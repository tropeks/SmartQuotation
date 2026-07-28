"""
O memorial ASME degrada, não desaparece (M1.3).

Regressão introduzida pelo M1: desde que a edição da EAP passou a emitir snapshot,
permutador pressurizado cujo memorial não monta dá **500 ao editar** — caminho que antes
funcionava, porque antes o override não construía snapshot.

Três defeitos somados:

1. `_requires_memorial` decide por truthiness do JSON cru; `memorial_asme` decide por
   `float()`. Um valor truthy mas não coercível ("50,0", "50 bar") faz o guard EXIGIR um
   memorial que o construtor não consegue montar. Os dois lados precisam concordar sobre
   o que é "ter pressão".
2. `corrosao_mm` era o único campo guardado por `is not None` em vez de `or`, então string
   vazia virava `float("")` → ValueError → memorial vazio.
3. O `try` envolvia o corpo inteiro, inclusive etapas OPCIONAIS e tardias (flange de corpo,
   radiografia). Uma falha ali descartava um memorial essencial já montado.

O princípio: um memorial com menos entradas é informação; um memorial vazio é falha. A
memória essencial (UG-21) depende só da pressão e não pode ser perdida por causa de um
campo acessório.
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase

from apps.quotations.services import _requires_memorial, build_snapshot_payload
from apps.tema_templates.services import memorial_asme


class _Cotacao:
    """Dublê mínimo: o guard só lê `scope` e `inputs`."""

    def __init__(self, inputs, scope="complete"):
        self.scope = scope
        self.inputs = inputs


BASE = {
    "designacao": "BEU", "pressao_projeto_bar": 50, "temperatura_projeto_c": 150,
    "diametro_casco_mm": 764, "esp_casco_mm": 9.5, "corrosao_mm": 3,
    "comprimento_casco_mm": 1631, "classe_casco": "CS",
}


class GuardEConstrutorConcordamTests(TenantTestCase):
    """O guard não pode exigir o que o construtor não consegue entregar."""

    def test_pressao_com_virgula_nao_exige_memorial(self):
        """'50,0' é truthy mas não vira float — o construtor devolve vazio."""
        self.assertFalse(_requires_memorial(_Cotacao({"pressao_projeto_bar": "50,0"})))

    def test_pressao_com_unidade_nao_exige_memorial(self):
        self.assertFalse(_requires_memorial(_Cotacao({"pressao_projeto_bar": "50 bar"})))

    def test_pressao_zero_como_texto_nao_exige_memorial(self):
        """'0' é truthy em Python, mas é pressão zero — equipamento não pressurizado."""
        self.assertFalse(_requires_memorial(_Cotacao({"pressao_projeto_bar": "0"})))

    def test_pressao_numerica_valida_continua_exigindo(self):
        self.assertTrue(_requires_memorial(_Cotacao({"pressao_projeto_bar": 50})))

    def test_pressao_como_texto_numerico_tambem_exige(self):
        """'50' coage para float — o construtor monta, então o guard deve exigir."""
        self.assertTrue(_requires_memorial(_Cotacao({"pressao_projeto_bar": "50"})))

    def test_escopo_diferente_de_completo_nunca_exige(self):
        self.assertFalse(
            _requires_memorial(_Cotacao({"pressao_projeto_bar": 50}, scope="tube_bundle")))


class MemorialDegradaTests(TenantTestCase):
    """Menos entradas é informação; vazio é falha."""

    def test_caso_completo_monta_o_memorial(self):
        self.assertGreater(len(memorial_asme("BEU", BASE)), 1)

    def test_corrosao_vazia_nao_apaga_o_memorial(self):
        """Era o campo mais frágil: `is not None` deixava '' chegar em float('')."""
        memorial = memorial_asme("BEU", dict(BASE, corrosao_mm=""))
        self.assertTrue(memorial, "string vazia em campo acessório não pode zerar tudo")

    def test_comprimento_invalido_nao_descarta_o_que_ja_foi_montado(self):
        """A radiografia é etapa tardia e opcional — falhar ali não pode apagar o UG-21."""
        memorial = memorial_asme("BEU", dict(BASE, comprimento_casco_mm="mil e seiscentos"))
        self.assertTrue(memorial)
        self.assertTrue(any("UG-21" in str(e.get("item", "")) or "Pressão" in str(e.get("item", ""))
                            for e in memorial),
                        "a memória essencial de pressão tem de sobreviver")

    def test_temperatura_invalida_nao_apaga_o_memorial(self):
        memorial = memorial_asme("BEU", dict(BASE, temperatura_projeto_c="ambiente"))
        self.assertTrue(memorial)

    def test_designacao_fora_do_catalogo_so_perde_o_flange(self):
        completo = memorial_asme("BEU", BASE)
        sem_catalogo = memorial_asme("XYZ", BASE)
        self.assertTrue(sem_catalogo)
        self.assertLessEqual(len(sem_catalogo), len(completo))

    def test_sem_pressao_continua_devolvendo_vazio(self):
        """Sem pressão não há memória de pressão a escrever — e o guard também não exige."""
        self.assertEqual(memorial_asme("BEU", {"designacao": "BEU"}), [])


class EditarPermutadorLegadoTests(TenantTestCase):
    """O caso que dava 500: cotação legada cujo input não coage."""

    def test_snapshot_de_cotacao_com_pressao_nao_coercivel_nao_explode(self):
        from apps.quotations.models import Customer, Quotation

        cliente = Customer.objects.create(company_name="Cliente Legado")
        q = Quotation.objects.create(
            number="COT-LEGADO", customer=cliente, title="Permutador legado",
            scope="complete",
            # Como ficaria uma linha gravada fora do formulário (admin, carga, migração).
            inputs=dict(BASE, pressao_projeto_bar="50,0"),
            custo_material=Decimal("100"), custo_mo=Decimal("50"),
            custo_total=Decimal("150"))

        payload = build_snapshot_payload(q)     # antes: RuntimeError → 500 no drawer

        self.assertIn("snapshot_hash", payload)

    def test_snapshot_de_permutador_pressurizado_valido_ainda_exige_memorial(self):
        """A trava de compliance continua de pé onde ela faz sentido."""
        from unittest.mock import patch

        from apps.quotations.models import Customer, Quotation

        cliente = Customer.objects.create(company_name="Cliente OK")
        q = Quotation.objects.create(
            number="COT-PRESS", customer=cliente, title="Permutador",
            scope="complete", inputs=dict(BASE),
            custo_material=Decimal("100"), custo_mo=Decimal("50"),
            custo_total=Decimal("150"))

        with patch("apps.tema_templates.services.memorial_asme", return_value=[]):
            with self.assertRaises(RuntimeError):
                build_snapshot_payload(q)


class EditarEapDePermutadorTests(TenantTestCase):
    """O buraco que deixou a regressão passar.

    Todos os testes do drawer rodavam sobre `create_feixe_quotation` — escopo
    `tube_bundle`, onde `_requires_memorial` é sempre False e o guard nunca é atingido.
    Nenhum exercitava a EAP de um permutador COMPLETO pressurizado, que é justamente a
    classe que passou a dar 500.
    """

    def setUp(self):
        from django.contrib.auth.models import User

        from apps.accounts.models import UserProfile
        from apps.quotations.models import Customer, Quotation, QuotationItem

        self.user = User.objects.create_user(username="orc_perm", password="x123456789")
        UserProfile.objects.create(user=self.user, full_name="Orç",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        cliente = Customer.objects.create(company_name="Cliente Permutador")
        self.quotation = Quotation.objects.create(
            number="COT-PERM-EAP", customer=cliente, title="Permutador pressurizado",
            scope="complete", inputs=dict(BASE),
            custo_material=Decimal("1000"), custo_mo=Decimal("500"),
            custo_total=Decimal("1500"))
        self.item = QuotationItem.objects.create(
            quotation=self.quotation, codigo_item="CASCO", descricao="Casco",
            custo_material=Decimal("1000"), custo_mo=Decimal("500"))
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.client.force_login(self.user)

    def test_drawer_de_permutador_pressurizado_salva(self):
        from django.urls import reverse

        resp = self.client.post(reverse("quotations:eap_item_save", args=[self.item.pk]),
                                {"motivo": "Ajuste conferido com o memorial."})

        self.assertEqual(resp.status_code, 200,
                         "editar a EAP de permutador pressurizado não pode dar 500")

    def test_drawer_de_permutador_com_input_legado_salva(self):
        """Pressão gravada como '50,0' — linha que não veio do formulário."""
        from django.urls import reverse

        self.quotation.inputs = dict(BASE, pressao_projeto_bar="50,0")
        self.quotation.save(update_fields=["inputs"])

        resp = self.client.post(reverse("quotations:eap_item_save", args=[self.item.pk]),
                                {"motivo": "Ajuste em cotação legada."})

        self.assertEqual(resp.status_code, 200)
