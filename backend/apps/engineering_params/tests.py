"""
Testes dos parâmetros de engenharia. Self-contained: cria linhas no setUp.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone
# TenantTestCase cria um schema de tenant de teste e roda dentro dele
# (tabelas de TENANT_APPS não existem no schema public).
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.engineering_params.models import ProcessParameter, Rate, RateSuggestion, TenantParamConfig
from apps.engineering_params.selectors import choose_drill_method, get_process_parameter

User = get_user_model()


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


class CalibrationViewTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        call_command("seed_engineering_params")
        self.today = timezone.localdate()

        self.engineer = User.objects.create_user(username="eng-cal", password="segredo123")
        UserProfile.objects.create(
            user=self.engineer,
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-123",
        )
        self.viewer = User.objects.create_user(username="orc-cal", password="segredo123")
        UserProfile.objects.create(user=self.viewer, role=UserProfile.ROLE_ORCAMENTISTA)

        self.current_rate = Rate.objects.filter(valid_until__isnull=True).order_by("operacao", "-valid_from").first()
        self.current_param = (
            ProcessParameter.objects.filter(valid_until__isnull=True)
            .order_by("operacao", "metodo", "material", "-valid_from")
            .first()
        )

        self.expired_rate = Rate.objects.create(
            operacao="ZZ_TEST_RATE_EXPIRADA",
            rate_hh=Decimal("10.00"),
            rate_hm=Decimal("5.00"),
            valid_from=date(2020, 1, 1),
            valid_until=self.today - timedelta(days=1),
        )
        self.future_rate = Rate.objects.create(
            operacao="ZZ_TEST_RATE_FUTURA",
            rate_hh=Decimal("99.00"),
            rate_hm=Decimal("9.00"),
            valid_from=self.today.replace(year=self.today.year + 1),
        )
        self.expired_param = ProcessParameter.objects.create(
            operacao="ZZ_TEST_PP_EXPIRADO",
            metodo="manual",
            material=None,
            valor=Decimal("1.2345"),
            unidade="fator",
            valid_from=date(2020, 1, 1),
            valid_until=self.today - timedelta(days=1),
        )

    def test_get_calibration_as_engineer_returns_200_with_current_rates_and_process_parameters(self):
        self.client.force_login(self.engineer)

        response = self.client.get("/engenharia/calibracao/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Taxas")
        self.assertContains(response, "Parâmetros de processo")
        self.assertContains(response, self.current_rate.operacao)
        self.assertContains(response, self.current_param.operacao)
        self.assertContains(response, self.current_param.get_metodo_display())
        self.assertNotContains(response, self.expired_rate.operacao)
        self.assertNotContains(response, self.future_rate.operacao)
        self.assertNotContains(response, self.expired_param.operacao)

    def test_get_calibration_without_permission_returns_403(self):
        self.client.force_login(self.viewer)

        response = self.client.get("/engenharia/calibracao/")

        self.assertEqual(response.status_code, 403)


class CalibrationRateEditViewTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        call_command("seed_engineering_params")
        self.today = timezone.localdate()

        self.editor = User.objects.create_user(username="eng-edit-rate", password="segredo123")
        UserProfile.objects.create(
            user=self.editor,
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-456",
        )
        self.viewer = User.objects.create_user(username="gestor-edit-rate", password="segredo123")
        UserProfile.objects.create(
            user=self.viewer,
            role=UserProfile.ROLE_GESTOR_COMERCIAL,
        )
        self.current_rate = Rate.objects.create(
            operacao="ZZ_EDIT_RATE",
            rate_hh=Decimal("111.11"),
            rate_hm=Decimal("22.22"),
            valid_from=self.today - timedelta(days=10),
            valid_until=None,
        )

    def test_post_novo_rate_hh_fecha_vigente_cria_historico_e_audita(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            f"/engenharia/calibracao/rates/{self.current_rate.pk}/",
            {
                "rate_hh": "321.99",
                "rate_hm": "123.45",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.current_rate.refresh_from_db()
        self.assertEqual(self.current_rate.valid_until, self.today - timedelta(days=1))

        rates = list(Rate.objects.filter(operacao=self.current_rate.operacao).order_by("valid_from", "id"))
        self.assertGreaterEqual(len(rates), 2)
        novo = rates[-1]
        self.assertNotEqual(novo.pk, self.current_rate.pk)
        self.assertEqual(novo.rate_hh, Decimal("321.99"))
        self.assertEqual(novo.rate_hm, Decimal("123.45"))
        self.assertEqual(novo.valid_from, self.today)
        self.assertIsNone(novo.valid_until)

        log = AccessLog.objects.get(action="rate_change")
        self.assertEqual(log.user, self.editor)
        self.assertEqual(log.resource_type, "Rate")
        self.assertEqual(log.resource_id, str(novo.pk))
        self.assertEqual(log.metadata["operacao"], self.current_rate.operacao)
        self.assertEqual(log.metadata["anterior"]["rate_hh"], str(self.current_rate.rate_hh))
        self.assertEqual(log.metadata["anterior"]["rate_hm"], str(self.current_rate.rate_hm))
        self.assertEqual(log.metadata["novo"]["rate_hh"], "321.99")
        self.assertEqual(log.metadata["novo"]["rate_hm"], "123.45")

    def test_post_sem_permissao_retorna_403_e_nao_altera_rate(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            f"/engenharia/calibracao/rates/{self.current_rate.pk}/",
            {
                "rate_hh": "321.99",
                "rate_hm": "123.45",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 403)
        self.current_rate.refresh_from_db()
        self.assertIsNone(self.current_rate.valid_until)
        self.assertEqual(
            Rate.objects.filter(operacao=self.current_rate.operacao, valid_until__isnull=True).count(),
            1,
        )
        self.assertFalse(AccessLog.objects.filter(action="rate_change").exists())

    def test_post_editar_rate_vigente_criado_hoje_atualiza_em_vez_de_duplicar(self):
        rate_de_hoje = Rate.objects.create(
            operacao="ZZ_EDIT_RATE_HOJE",
            rate_hh=Decimal("50.00"),
            rate_hm=Decimal("15.00"),
            valid_from=self.today,
            valid_until=None,
        )
        self.client.force_login(self.editor)

        response = self.client.post(
            f"/engenharia/calibracao/rates/{rate_de_hoje.pk}/",
            {
                "rate_hh": "321.99",
                "rate_hm": "123.45",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        rate_de_hoje.refresh_from_db()
        self.assertEqual(rate_de_hoje.rate_hh, Decimal("321.99"))
        self.assertEqual(rate_de_hoje.rate_hm, Decimal("123.45"))
        self.assertEqual(rate_de_hoje.valid_from, self.today)
        self.assertIsNone(rate_de_hoje.valid_until)
        self.assertEqual(Rate.objects.filter(operacao="ZZ_EDIT_RATE_HOJE").count(), 1)

        log = AccessLog.objects.get(action="rate_change", resource_id=str(rate_de_hoje.pk))
        self.assertEqual(log.metadata["anterior"]["rate_hh"], "50.00")
        self.assertEqual(log.metadata["novo"]["rate_hh"], "321.99")


class CalibrationProcessParameterEditViewTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        call_command("seed_engineering_params")
        self.today = timezone.localdate()

        self.editor = User.objects.create_user(username="eng-edit-param", password="segredo123")
        UserProfile.objects.create(
            user=self.editor,
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-789",
        )
        self.viewer = User.objects.create_user(username="gestor-edit-param", password="segredo123")
        UserProfile.objects.create(
            user=self.viewer,
            role=UserProfile.ROLE_GESTOR_COMERCIAL,
        )
        self.current_param = ProcessParameter.objects.create(
            operacao="ZZ_EDIT_PARAM",
            metodo="radial",
            material=None,
            valor=Decimal("40.0000"),
            unidade="mm/min",
            descricao="avanço de teste",
            valid_from=self.today - timedelta(days=10),
            valid_until=None,
        )

    def test_post_novo_valor_fecha_vigente_cria_historico_e_audita(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            f"/engenharia/calibracao/process-parameters/{self.current_param.pk}/",
            {"valor": "55,5000"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.current_param.refresh_from_db()
        self.assertEqual(self.current_param.valid_until, self.today - timedelta(days=1))

        params = list(
            ProcessParameter.objects.filter(
                operacao=self.current_param.operacao, metodo=self.current_param.metodo
            ).order_by("valid_from", "id")
        )
        self.assertGreaterEqual(len(params), 2)
        novo = params[-1]
        self.assertNotEqual(novo.pk, self.current_param.pk)
        self.assertEqual(novo.valor, Decimal("55.5000"))
        self.assertEqual(novo.valid_from, self.today)
        self.assertIsNone(novo.valid_until)
        self.assertEqual(novo.material, self.current_param.material)
        self.assertEqual(novo.unidade, self.current_param.unidade)

        log = AccessLog.objects.get(action="param_change")
        self.assertEqual(log.user, self.editor)
        self.assertEqual(log.resource_type, "ProcessParameter")
        self.assertEqual(log.resource_id, str(novo.pk))
        self.assertEqual(log.metadata["operacao"], self.current_param.operacao)
        self.assertEqual(log.metadata["metodo"], self.current_param.metodo)
        self.assertEqual(log.metadata["anterior"]["valor"], str(self.current_param.valor))
        self.assertEqual(log.metadata["novo"]["valor"], "55.5000")

    def test_post_sem_permissao_retorna_403_e_nao_altera_parametro(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            f"/engenharia/calibracao/process-parameters/{self.current_param.pk}/",
            {"valor": "55,5000"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 403)
        self.current_param.refresh_from_db()
        self.assertIsNone(self.current_param.valid_until)
        self.assertEqual(
            ProcessParameter.objects.filter(
                operacao=self.current_param.operacao,
                metodo=self.current_param.metodo,
                valid_until__isnull=True,
            ).count(),
            1,
        )
        self.assertFalse(AccessLog.objects.filter(action="param_change").exists())

    def test_post_editar_param_vigente_criado_hoje_atualiza_em_vez_de_duplicar(self):
        param_de_hoje = ProcessParameter.objects.create(
            operacao="ZZ_EDIT_PARAM_HOJE",
            metodo="radial",
            material=None,
            valor=Decimal("40.0000"),
            unidade="mm/min",
            descricao="avanço de teste",
            valid_from=self.today,
            valid_until=None,
        )
        self.client.force_login(self.editor)

        response = self.client.post(
            f"/engenharia/calibracao/process-parameters/{param_de_hoje.pk}/",
            {"valor": "99,9000"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        param_de_hoje.refresh_from_db()
        self.assertEqual(param_de_hoje.valor, Decimal("99.9000"))
        self.assertEqual(param_de_hoje.valid_from, self.today)
        self.assertIsNone(param_de_hoje.valid_until)
        self.assertEqual(
            ProcessParameter.objects.filter(operacao="ZZ_EDIT_PARAM_HOJE").count(), 1
        )

        log = AccessLog.objects.get(action="param_change", resource_id=str(param_de_hoje.pk))
        self.assertEqual(log.metadata["anterior"]["valor"], "40.0000")
        self.assertEqual(log.metadata["novo"]["valor"], "99.9000")


class CalibrationSuggestionAcceptViewTests(TestCase):
    """EPICO 4 T5: integra RateSuggestion na aba Taxas da calibração."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.today = timezone.localdate()

        self.editor = User.objects.create_user(username="eng-accept-sugg", password="segredo123")
        UserProfile.objects.create(
            user=self.editor,
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-999",
        )
        self.viewer = User.objects.create_user(username="orc-accept-sugg", password="segredo123")
        UserProfile.objects.create(user=self.viewer, role=UserProfile.ROLE_ORCAMENTISTA)

        self.current_rate = Rate.objects.create(
            operacao="ZZ_SUGGESTION_OP",
            rate_hh=Decimal("100.00"),
            rate_hm=Decimal("10.00"),
            valid_from=self.today - timedelta(days=30),
            valid_until=None,
        )
        self.suggestion = RateSuggestion.objects.create(
            operacao="ZZ_SUGGESTION_OP",
            actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"),
            delta_pct=Decimal("15.00"),
            n_samples=25,
            confidence=Decimal("0.80"),
        )

    def test_get_calibration_rates_tab_lista_sugestao_pendente(self):
        self.client.force_login(self.editor)

        response = self.client.get("/engenharia/calibracao/?tab=rates")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ZZ_SUGGESTION_OP")
        self.assertContains(response, "Aceitar sugestão")

    def test_post_aceitar_sugestao_cria_nova_versao_fecha_vigente_e_audita_apontamento(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            f"/engenharia/calibracao/sugestoes/{self.suggestion.pk}/aceitar/",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)

        self.current_rate.refresh_from_db()
        self.assertEqual(self.current_rate.valid_until, self.today - timedelta(days=1))

        novo = Rate.objects.vigente("ZZ_SUGGESTION_OP")
        self.assertNotEqual(novo.pk, self.current_rate.pk)
        self.assertEqual(novo.rate_hh, Decimal("115.00"))
        self.assertEqual(novo.valid_from, self.today)
        self.assertIsNone(novo.valid_until)

        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, "accepted")
        self.assertEqual(self.suggestion.resolved_by, self.editor)
        self.assertIsNotNone(self.suggestion.resolved_at)

        log = AccessLog.objects.get(action="rate_change", resource_id=str(novo.pk))
        self.assertEqual(log.metadata["origem"], "apontamento")
        self.assertEqual(log.metadata["operacao"], "ZZ_SUGGESTION_OP")

    def test_post_aceitar_sugestao_sem_permissao_retorna_403(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            f"/engenharia/calibracao/sugestoes/{self.suggestion.pk}/aceitar/",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 403)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, "pending")

    def test_post_aceitar_sugestao_ja_resolvida_retorna_404(self):
        self.suggestion.status = "accepted"
        self.suggestion.save(update_fields=["status"])
        self.client.force_login(self.editor)

        response = self.client.post(
            f"/engenharia/calibracao/sugestoes/{self.suggestion.pk}/aceitar/",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 404)
