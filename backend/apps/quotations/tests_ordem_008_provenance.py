"""Ordem 008 (rodada de conserto, a partir da revisão do Diretor) — `revise_complete`
(adapter.py) congelava `orig.fator_preco`/`.impostos_pct` sem checar a PROVENIÊNCIA desses
campos.

O defeito: `Quotation.fator_preco`/`.impostos_pct` são campos do MODEL com default
`1,01377`/`23,303` — os valores do FEIXE, não do permutador. Uma `Quotation(scope="complete")`
criada FORA de `persist_complete` (admin "add", carga, migração de dados — o mesmo caminho
real exercitado por `tests_memorial_robusto.py:113-166`, que cria uma `Quotation` `complete`
via `Quotation.objects.create(...)` sem passar `fator_preco`/`impostos_pct`) nasce com esse
default sem nunca ter passado pelo motor do permutador. `revise_complete` congelava esse
valor como se fosse markup/ICMS do permutador — um preço de venda ~19% errado, sem aviso.

Regra nova: congelar o par da original só quando ela tem PROVENIÊNCIA do motor — lida do
`CalculationSnapshot` mais recente (`inputs.pricing.fator_preco`/`.impostos_pct`, o que de
fato precificou). Sem snapshot, usa o markup VIGENTE do tenant (`tenant_pricing_completo()`)
e registra `logger.warning` com o número/revisão da cotação.
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase as TestCase

from apps.engineering_params.models import TenantParamConfig
from apps.quotations.models import Customer, Quotation

# cleaned válido p/ PermutadorDataSheetForm — mesmo usado em tema_templates/tests_ordem_008.py
CLEANED_BEU = {
    "designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
    "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 18,
    "comprimento_casco_mm": 1631, "diametro_casco_mm": 764,
    "esp_casco_mm": 9.5, "n_passes_tubos": 2, "rt_escopo": "Parcial",
    "classe_feixe": "CS", "classe_casco": "CS", "fluido_corrosivo": "Tubos",
    "fator_correcao_mo": 1.0,
}


class RevisaoSemProvenienciaUsaMarkupDoTenantTests(TestCase):
    """(a) original 'complete' sem CalculationSnapshot (nunca passou pelo motor) — a
    revisão não pode congelar o default do MODEL (valores do feixe); usa o vigente do
    tenant, com aviso."""

    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME Sem Proveniencia")

    def _criar_sem_persist_complete(self) -> Quotation:
        """Simula admin 'add'/carga/migração: cria a linha direto, sem passar por
        `persist_complete` — nasce SEM snapshot e com o default do MODEL (1,01377/23,303,
        os valores do FEIXE), o mesmo caminho de `tests_memorial_robusto.py`."""
        return Quotation.objects.create(
            number="COT-2026-SEMPROV", revision=0, customer=self.customer, scope="complete",
            title="BEU sem proveniência", inputs=dict(CLEANED_BEU),
            custo_material=Decimal("1.00"), custo_mo=Decimal("1.00"), custo_total=Decimal("2.00"),
            preco_sem_impostos=Decimal("2.00"), preco_com_impostos=Decimal("2.00"),
        )

    def test_original_sem_snapshot_tem_o_default_do_feixe(self):
        """Prova a premissa do defeito: o default do MODEL É o do feixe, não o do permutador."""
        orig = self._criar_sem_persist_complete()
        self.assertEqual(orig.fator_preco, Decimal("1.01377"))
        self.assertEqual(orig.impostos_pct, Decimal("23.303"))
        self.assertEqual(orig.snapshots.count(), 0)

    def test_revisao_usa_o_markup_vigente_do_tenant_nao_o_default_do_feixe(self):
        from apps.quotations.adapter import revise_complete

        orig = self._criar_sem_persist_complete()

        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("1.30")
        cfg.impostos_pct_completo = Decimal("12")
        cfg.save()

        with self.assertLogs("apps.quotations.adapter", level="WARNING") as logs:
            rev = revise_complete(orig, created_by=None)

        self.assertEqual(rev.fator_preco, Decimal("1.30000"))
        self.assertEqual(rev.impostos_pct, Decimal("12.000"))
        # NÃO congelou o default do feixe que a original tinha
        self.assertNotEqual(rev.fator_preco, Decimal("1.01377"))
        self.assertTrue(any(orig.number in msg for msg in logs.output))


class RevisaoComProvenienciaCongelaOSnapshotTests(TestCase):
    """(b) original com snapshot (criada via persist_complete de verdade) — a revisão
    continua congelando o par DO SNAPSHOT, mesmo que o tenant já tenha mudado de política
    comercial. Já era o comportamento esperado da ordem 008 original; prova que a regra de
    proveniência não regride esse caso."""

    def setUp(self):
        self.customer, _ = Customer.objects.get_or_create(company_name="ACME Com Proveniencia")

    def test_revisao_congela_o_par_do_snapshot_apesar_do_tenant_mudar(self):
        from apps.quotations.adapter import persist_complete, revise_complete
        from apps.tema_templates.services import estimate_from_inputs

        cfg = TenantParamConfig.get_solo()
        cfg.fator_preco_completo = Decimal("1.30")
        cfg.impostos_pct_completo = Decimal("12")
        cfg.save()

        resultado = estimate_from_inputs("BEU", CLEANED_BEU)
        orig = persist_complete(self.customer, "BEU", CLEANED_BEU, resultado)
        self.assertGreater(orig.snapshots.count(), 0)
        custo_orig = orig.custo_total

        # tenant muda de política comercial DEPOIS de criar a cotação original
        cfg.fator_preco_completo = Decimal("1.40")
        cfg.impostos_pct_completo = Decimal("15")
        cfg.save()

        rev = revise_complete(orig, created_by=None)

        self.assertEqual(rev.fator_preco, Decimal("1.30000"))
        self.assertEqual(rev.impostos_pct, Decimal("12.000"))
        self.assertAlmostEqual(float(rev.preco_com_impostos), float(custo_orig) * 1.30, delta=2.0)
