"""Ordem 008 — markup/impostos do tenant no motor do permutador completo.

Decisões do Diretor (ver .maestro/orders/008-*.md):
(a) só o par do permutador: TenantParamConfig.fator_preco_completo/impostos_pct_completo.
(b) mantêm-se as duas semânticas de imposto (feixe por fora, permutador por dentro/ICMS).
(c) revise_complete congela o markup/imposto da cotação ORIGINAL.
(d) default 1,25/9,0 — preço não muda no dia 1.

O motor (pricing_engine) NÃO lê TenantCostChain.fator_preco/.impostos_pct — os valores do
tenant são passados EXPLICITAMENTE como kwargs de quote_completo (TenantCostChain tem
defaults neutros 1,0/0,0 que zerariam o markup em silêncio).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.engineering_params.models import TenantParamConfig
from pricing_engine.permutador_quote import gross_up_icms, quote_completo

# cleaned válido p/ PermutadorDataSheetForm, sem pressão (evita exigir memorial ASME no
# persist_complete) — mesmo cleaned usado em tests.py:test_recompute_complete_preserva_...
CLEANED_BEU = {
    "designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
    "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 18,
    "comprimento_casco_mm": 1631, "diametro_casco_mm": 764,
    "esp_casco_mm": 9.5, "n_passes_tubos": 2, "rt_escopo": "Parcial",
    "classe_feixe": "CS", "classe_casco": "CS", "fluido_corrosivo": "Tubos",
    "fator_correcao_mo": 1.0,
}


class TenantParamConfigCamposOrdem008Tests(TestCase):
    """Campos novos fator_preco_completo/impostos_pct_completo em TenantParamConfig."""

    def test_default_identico_ao_hardcoded_de_hoje(self):
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.fator_preco_completo, Decimal("1.25000"))
        self.assertEqual(cfg.impostos_pct_completo, Decimal("9.000"))

    def test_fator_preco_completo_deve_ser_maior_que_zero(self):
        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("0")
        with self.assertRaises(ValidationError):
            cfg.full_clean()

    def test_fator_preco_completo_negativo_invalido(self):
        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("-1.5")
        with self.assertRaises(ValidationError):
            cfg.full_clean()

    def test_impostos_pct_completo_100_invalido(self):
        cfg = TenantParamConfig.get_solo()
        cfg.impostos_pct_completo = Decimal("100")
        with self.assertRaises(ValidationError):
            cfg.full_clean()

    def test_impostos_pct_completo_negativo_invalido(self):
        cfg = TenantParamConfig.get_solo()
        cfg.impostos_pct_completo = Decimal("-1")
        with self.assertRaises(ValidationError):
            cfg.full_clean()

    def test_impostos_pct_completo_zero_valido(self):
        cfg = TenantParamConfig.get_solo()
        cfg.impostos_pct_completo = Decimal("0")
        cfg.full_clean()   # não levanta


class EstimateCompleteUsaMarkupDoTenantTests(TestCase):
    """tema_templates.estimate_complete passa fator_preco/impostos_pct do tenant ao motor."""

    def test_sem_configuracao_preco_igual_ao_de_hoje(self):
        """Tenant novo (default 1,25/9,0) → mesmo preço que o motor hardcoded de sempre."""
        from apps.tema_templates.services import estimate_complete
        de_hoje = quote_completo("BEU")   # defaults de função do motor: 1,25/9,0
        com_tenant = estimate_complete("BEU")
        preco_com = com_tenant["preco_com_impostos"]
        preco_sem = com_tenant["preco_sem_impostos"]
        self.assertAlmostEqual(preco_com, de_hoje["preco_com_impostos"], places=2)
        self.assertAlmostEqual(preco_sem, de_hoje["preco_sem_impostos"], places=2)
        self.assertEqual(com_tenant["fator_preco"], 1.25)
        self.assertEqual(com_tenant["impostos_pct"], 9.0)

    def test_tenant_1_30_12_muda_o_preco(self):
        from apps.tema_templates.services import estimate_complete
        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("1.30")
        cfg.impostos_pct_completo = Decimal("12")
        cfg.save()

        r = estimate_complete("BEU")
        custo_total = r["custo_total"]
        preco_sem_esperado = (custo_total * 1.30) / gross_up_icms(12.0)
        self.assertAlmostEqual(r["preco_com_impostos"], custo_total * 1.30, places=1)
        self.assertAlmostEqual(r["preco_sem_impostos"], preco_sem_esperado, places=1)
        self.assertEqual(r["fator_preco"], 1.30)
        self.assertEqual(r["impostos_pct"], 12.0)

    def test_compose_check_preview_reflete_tenant(self):
        """O preview da tela Compor (compose_check) usa estimate_complete sem override
        nenhum — muda o markup do tenant, o número exibido no preview HTMX muda junto."""
        call_command("seed_tema_catalog")
        User = get_user_model()
        u = User.objects.create_user(username="eng008", password="x")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=u, full_name="Eng", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.client.login(username="eng008", password="x")

        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("1.30")
        cfg.impostos_pct_completo = Decimal("12")
        cfg.save()

        r = self.client.post("/tema/compor/check/", {"front": "B", "shell": "E", "rear": "U"})
        self.assertContains(r, "markup 1.3")


class ReviseCompleteCongelaMarkupTests(TestCase):
    """revise_complete recalcula com o fator_preco/impostos_pct da cotação ORIGINAL,
    não com o vigente do tenant (paridade com revise_feixe — decisão (c) do Diretor)."""

    def setUp(self):
        from apps.quotations.models import Customer
        self.customer, _ = Customer.objects.get_or_create(company_name="ACME Ordem 008")

    def _criar_original(self):
        from apps.quotations.adapter import persist_complete
        from apps.tema_templates.services import estimate_from_inputs

        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("1.30")
        cfg.impostos_pct_completo = Decimal("12")
        cfg.save()

        resultado = estimate_from_inputs("BEU", CLEANED_BEU)
        return persist_complete(self.customer, "BEU", CLEANED_BEU, resultado)

    def test_snapshot_pricing_grava_o_markup_do_tenant_na_criacao(self):
        q = self._criar_original()
        self.assertEqual(q.fator_preco, Decimal("1.30000"))
        self.assertEqual(q.impostos_pct, Decimal("12.000"))
        snap = q.snapshots.first()
        esperado = {"fator_preco": "1.30000", "impostos_pct": "12.000"}
        self.assertEqual(snap.inputs["pricing"], esperado)

    def test_revisao_congela_markup_original_mesmo_apos_tenant_mudar(self):
        from apps.quotations.adapter import revise_complete

        orig = self._criar_original()
        custo_orig = orig.custo_total

        # tenant muda de política comercial DEPOIS de criar a cotação original
        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("1.40")
        cfg.impostos_pct_completo = Decimal("15")
        cfg.save()

        rev = revise_complete(orig, created_by=None)

        self.assertEqual(rev.fator_preco, Decimal("1.30000"))
        self.assertEqual(rev.impostos_pct, Decimal("12.000"))
        # o preço da revisão segue a fórmula ORIGINAL (1,30/12), não a vigente (1,40/15)
        self.assertAlmostEqual(float(rev.preco_com_impostos), float(custo_orig) * 1.30, delta=2.0)
