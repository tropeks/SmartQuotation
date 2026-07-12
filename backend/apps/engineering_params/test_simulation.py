"""
Testes do EPICO 4 (impacto simulado): recotar o golden case com o valor PROPOSTO de
Rate/ProcessParameter, sem persistir nada (nem Rate/PP, nem Quotation/EAP).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.engineering_params.models import ProcessParameter, Rate
from apps.engineering_params.simulation import (
    simulate_process_parameter_change,
    simulate_rate_change,
)
from apps.quotations.models import Quotation

User = get_user_model()


class SimulateRateChangeServiceTests(TestCase):
    def setUp(self):
        call_command("seed_engineering_params")
        self.rate = Rate.objects.filter(operacao="FURAR_ESPELHO", valid_until__isnull=True).get()

    def test_aumento_de_rate_hh_produz_delta_positivo(self):
        result = simulate_rate_change(
            "FURAR_ESPELHO", rate_hh=self.rate.rate_hh + Decimal("500.00")
        )
        self.assertGreater(result["delta_custo"], Decimal("0"))
        self.assertGreater(result["custo_total_proposto"], result["custo_total_atual"])

    def test_reducao_de_rate_hh_produz_delta_negativo(self):
        result = simulate_rate_change(
            "FURAR_ESPELHO", rate_hh=max(self.rate.rate_hh - Decimal("50.00"), Decimal("1.00"))
        )
        self.assertLess(result["delta_custo"], Decimal("0"))

    def test_simulacao_nao_persiste_rate_no_banco(self):
        original_rate_hh = self.rate.rate_hh
        rows_antes = Rate.objects.filter(operacao="FURAR_ESPELHO").count()

        simulate_rate_change("FURAR_ESPELHO", rate_hh=self.rate.rate_hh + Decimal("999.00"))

        self.rate.refresh_from_db()
        self.assertEqual(self.rate.rate_hh, original_rate_hh)
        self.assertEqual(Rate.objects.filter(operacao="FURAR_ESPELHO").count(), rows_antes)

    def test_simulacao_nao_cria_nem_recomputa_cotacao(self):
        antes = Quotation.objects.count()
        simulate_rate_change("FURAR_ESPELHO", rate_hh=self.rate.rate_hh + Decimal("500.00"))
        self.assertEqual(Quotation.objects.count(), antes)


class SimulateProcessParameterChangeServiceTests(TestCase):
    def setUp(self):
        call_command("seed_engineering_params")
        self.pp = ProcessParameter.objects.filter(
            operacao="FURAR_ESPELHO", metodo="radial", material__isnull=True, valid_until__isnull=True
        ).get()

    def test_alteracao_de_valor_muda_custo_sem_persistir(self):
        novo_valor = (self.pp.valor or Decimal("1")) * Decimal("2")
        result = simulate_process_parameter_change(
            "FURAR_ESPELHO", "radial", None, novo_valor
        )
        self.assertNotEqual(result["delta_custo"], Decimal("0"))

        self.pp.refresh_from_db()
        self.assertNotEqual(self.pp.valor, novo_valor)


class PreviewRateImpactViewTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        call_command("seed_engineering_params")
        self.today = timezone.localdate()

        self.editor = User.objects.create_user(username="eng-preview", password="segredo123")
        UserProfile.objects.create(user=self.editor, role=UserProfile.ROLE_ENGENHEIRO, crea_number="CREA-789")
        self.viewer = User.objects.create_user(username="orc-preview", password="segredo123")
        UserProfile.objects.create(user=self.viewer, role=UserProfile.ROLE_ORCAMENTISTA)

        self.rate = Rate.objects.filter(operacao="FURAR_ESPELHO", valid_until__isnull=True).get()

    def test_preview_rate_como_engenheiro_mostra_delta_e_nao_persiste(self):
        self.client.force_login(self.editor)
        rate_hh_original = self.rate.rate_hh

        response = self.client.post(
            f"/engenharia/calibracao/rates/{self.rate.pk}/preview/",
            {"rate_hh": str(self.rate.rate_hh + Decimal("500.00")), "rate_hm": str(self.rate.rate_hm or "")},
        )

        self.assertEqual(response.status_code, 200)
        self.rate.refresh_from_db()
        self.assertEqual(self.rate.rate_hh, rate_hh_original)
        self.assertEqual(
            Rate.objects.filter(operacao="FURAR_ESPELHO", valid_until__isnull=True).count(), 1
        )

    def test_preview_rate_sem_permissao_retorna_403(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            f"/engenharia/calibracao/rates/{self.rate.pk}/preview/",
            {"rate_hh": str(self.rate.rate_hh + Decimal("500.00"))},
        )

        self.assertEqual(response.status_code, 403)

    def test_preview_rate_nao_recomputa_nenhuma_cotacao(self):
        self.client.force_login(self.editor)
        antes = Quotation.objects.count()

        self.client.post(
            f"/engenharia/calibracao/rates/{self.rate.pk}/preview/",
            {"rate_hh": str(self.rate.rate_hh + Decimal("500.00"))},
        )

        self.assertEqual(Quotation.objects.count(), antes)
