"""
Testes dos parâmetros de engenharia. Self-contained: cria linhas no setUp.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
# TenantTestCase cria um schema de tenant de teste e roda dentro dele
# (tabelas de TENANT_APPS não existem no schema public).
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.engineering_params.models import ProcessParameter, Rate, TenantParamConfig
from apps.engineering_params.selectors import choose_drill_method, get_process_parameter


class RateVigenteTests(TestCase):
    def setUp(self):
        # rate antigo, encerrado em 2025-12-31
        self.antigo = Rate.objects.create(
            operacao="FURAR_ESPELHO",
            rate_hh=Decimal("100.00"),
            rate_hm=Decimal("70.00"),
            valid_from=date(2025, 1, 1),
            valid_until=date(2025, 12, 31),
        )
        # rate atual, vigente a partir de 2026-01-01 sem fim
        self.atual = Rate.objects.create(
            operacao="FURAR_ESPELHO",
            rate_hh=Decimal("110.00"),
            rate_hm=Decimal("80.00"),
            valid_from=date(2026, 1, 1),
        )

    def test_vigente_retorna_rate_atual(self):
        r = Rate.objects.vigente("FURAR_ESPELHO", on_date=date(2026, 6, 5))
        self.assertIsNotNone(r)
        self.assertEqual(r.pk, self.atual.pk)
        self.assertEqual(r.rate_hh, Decimal("110.00"))

    def test_vigente_respeita_valid_until(self):
        r = Rate.objects.vigente("FURAR_ESPELHO", on_date=date(2025, 6, 1))
        self.assertEqual(r.pk, self.antigo.pk)
        self.assertEqual(r.rate_hh, Decimal("100.00"))

    def test_vigente_antes_de_qualquer_rate_retorna_none(self):
        r = Rate.objects.vigente("FURAR_ESPELHO", on_date=date(2024, 1, 1))
        self.assertIsNone(r)

    def test_vigente_operacao_inexistente(self):
        self.assertIsNone(Rate.objects.vigente("NAO_EXISTE"))


class ProcessParameterLookupTests(TestCase):
    def setUp(self):
        ProcessParameter.objects.create(
            operacao="FURAR_ESPELHO", metodo="radial", material=None, valor=Decimal("40.0000"),
            unidade="mm/min", descricao="avanço furadeira radial",
        )
        ProcessParameter.objects.create(
            operacao="FURAR_ESPELHO", metodo="cnc", material=None, valor=Decimal("97.5600"),
            unidade="mm/min", descricao="avanço furação CNC",
        )
        ProcessParameter.objects.create(
            operacao="FURAR_ESPELHO", metodo="cnc", material="AISI316", valor=Decimal("88.0000"),
            unidade="mm/min", descricao="avanço furação CNC por material",
        )

    def test_lookup_por_operacao_e_metodo(self):
        pp = ProcessParameter.objects.get(operacao="FURAR_ESPELHO", metodo="radial")
        self.assertEqual(pp.valor, Decimal("40.0000"))
        self.assertEqual(pp.unidade, "mm/min")

    def test_valor_cnc_confirmado(self):
        pp = ProcessParameter.objects.get(operacao="FURAR_ESPELHO", metodo="cnc", material=None)
        self.assertEqual(pp.valor, Decimal("97.5600"))

    def test_material_especifico_vence_fallback(self):
        pp = get_process_parameter("FURAR_ESPELHO", "cnc", material="AISI316")
        self.assertEqual(pp.valor, Decimal("88.0000"))

    def test_material_desconhecido_cai_no_fallback(self):
        pp = get_process_parameter("FURAR_ESPELHO", "cnc", material="AISI304")
        self.assertEqual(pp.valor, Decimal("97.5600"))

    def test_sem_material_mantem_comportamento(self):
        pp = get_process_parameter("FURAR_ESPELHO", "cnc")
        self.assertEqual(pp.valor, Decimal("97.5600"))

    def test_alargar_espelho_cnc_bloqueado_no_model(self):
        pp = ProcessParameter(
            operacao="ALARGAR_ESPELHO", metodo="cnc", valor=Decimal("70.0000"),
            unidade="mm/min",
        )
        with self.assertRaises(ValidationError):
            pp.full_clean()


class ChooseDrillMethodTests(TestCase):
    def test_limiar_600_radial(self):
        self.assertEqual(choose_drill_method(600), "radial")

    def test_601_cnc(self):
        self.assertEqual(choose_drill_method(601), "cnc")

    def test_override_vence(self):
        self.assertEqual(choose_drill_method(601, override="radial"), "radial")
        self.assertEqual(choose_drill_method(10, override="cnc"), "cnc")

    def test_threshold_do_tenant_config(self):
        cfg = TenantParamConfig.get_solo()
        cfg.drill_method_threshold_holes = 100
        cfg.save()
        # threshold=None força a leitura do TenantParamConfig
        self.assertEqual(choose_drill_method(150, threshold=None), "cnc")
        self.assertEqual(choose_drill_method(100, threshold=None), "radial")


class TenantParamConfigTests(TestCase):
    def test_get_solo_idempotente(self):
        a = TenantParamConfig.get_solo()
        b = TenantParamConfig.get_solo()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(TenantParamConfig.objects.count(), 1)

    def test_defaults(self):
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.fator_correcao_mo, Decimal("1.0000"))
        self.assertEqual(cfg.drill_method_threshold_holes, 600)

    def test_save_mantem_singleton(self):
        cfg = TenantParamConfig.get_solo()
        cfg.drill_method_threshold_holes = 700
        cfg.save()
        self.assertEqual(TenantParamConfig.objects.count(), 1)
        self.assertEqual(TenantParamConfig.get_solo().drill_method_threshold_holes, 700)


class CncDrillFeedGuardTests(SimpleTestCase):
    """Guarda anti-drift dos avanços CNC de furação (Wellington, 2026-06-19) no motor puro.
    Trava a causa raiz do crash em espelho grande: nenhum avanço CNC pode voltar a ser None."""

    def test_avancos_cnc_validados_pelo_pe(self):
        from pricing_engine import process_params as pp
        self.assertAlmostEqual(pp.get("FURAR_ESPELHO", pp.CNC), 97.56)
        self.assertAlmostEqual(pp.get("FURAR_CHICANA", pp.CNC), 83.34)
        with self.assertRaises(KeyError):
            pp.get("ALARGAR_ESPELHO", pp.CNC)

    def test_nenhum_avanco_cnc_de_furacao_e_none(self):
        """>600 furos seleciona CNC; se algum avanço fosse None, a cotação quebraria."""
        from pricing_engine import process_params as pp
        for op in ("FURAR_ESPELHO", "FURAR_CHICANA"):
            self.assertIsNotNone(pp.get(op, pp.CNC), f"{op} CNC não pode ser None")

    def test_alargamento_cnc_nao_existe_como_etapa(self):
        from pricing_engine.feixe_inputs import FeixeInputs
        from pricing_engine.operations import alargar_espelho_horas
        from pricing_engine.operations_registry import REGISTRY

        self.assertEqual(alargar_espelho_horas(601, 44.5), 0)
        op = next(o for o in REGISTRY if o.code == "OP-ESP-ALARGAR")
        self.assertFalse(op.applicable(FeixeInputs(n_tubos=601, n_espelhos=1)))

    def test_furacao_cnc_nao_e_mais_lenta_que_radial(self):
        """Sanidade física: o avanço CNC de furação ≥ radial (CNC não pode ser mais lento)."""
        from pricing_engine import process_params as pp
        for op in ("FURAR_ESPELHO", "FURAR_CHICANA"):
            self.assertGreaterEqual(pp.get(op, pp.CNC), pp.get(op, pp.RADIAL))
