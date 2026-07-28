"""
A conciliação mede pelas OFs ENTREGUES no período (S3.1).

O comando filtrava por `Quotation.created_at` — a data em que a cotação foi CRIADA. Mas
as horas da folha foram gastas produzindo o que a fábrica ENTREGOU naquele período. Uma
cotação criada em março e entregue em junho caía no balde errado, e o fator de correção
saía enviesado nas duas pontas: faltavam horas de um lado, sobravam do outro.

`OrdemFabricacao.completed_at` é populado na transição para "concluída"
(`production/services.py:308`), então a data de entrega existe e é confiável.
"""
from datetime import date, datetime, timedelta, timezone as tz
from decimal import Decimal

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.services import approve_quotation
from apps.cost_discovery.reconciliacao import horas_estimadas_de, cotacoes_entregues_em
from apps.production.models import STATUS_CONCLUIDA, OrdemFabricacao
from apps.production.services import convert_quotation_to_of
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation

SENHA = "x123456789"


class PeriodoPelaEntregaTests(TenantTestCase):
    def setUp(self):
        self.eng = User.objects.create_user(username="eng_per", password=SENHA)
        self.perfil = UserProfile.objects.create(
            user=self.eng, full_name="Eng", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-PER/SP", crea_state="SP")
        self.customer = Customer.objects.create(company_name="Cliente Período")

    def _of_entregue_em(self, titulo, quando):
        q = create_feixe_quotation(self.customer, titulo, created_by=self.eng)
        approve_quotation(q, self.perfil, art_number=f"ART-{titulo}")
        of = convert_quotation_to_of(q, created_by=self.eng)
        OrdemFabricacao.objects.filter(pk=of.pk).update(
            status=STATUS_CONCLUIDA,
            completed_at=datetime.combine(quando, datetime.min.time(), tzinfo=tz.utc))
        return q, of

    def test_conta_a_of_entregue_no_periodo(self):
        q, _of = self._of_entregue_em("Entregue em maio", date(2026, 5, 15))

        cotacoes = cotacoes_entregues_em(date(2026, 5, 1), date(2026, 5, 31))

        self.assertIn(q.pk, [c.pk for c in cotacoes])

    def test_ignora_o_que_foi_entregue_fora_do_periodo(self):
        self._of_entregue_em("Entregue em março", date(2026, 3, 10))

        cotacoes = cotacoes_entregues_em(date(2026, 5, 1), date(2026, 5, 31))

        self.assertEqual(len(cotacoes), 0)

    def test_criada_antes_e_entregue_dentro_conta(self):
        """O caso que a data de criação errava: cotação velha, entrega no período."""
        q, of = self._of_entregue_em("Criada antes", date(2026, 6, 20))
        OrdemFabricacao.objects.filter(pk=of.pk).update(
            created_at=datetime(2026, 1, 5, tzinfo=tz.utc))

        cotacoes = cotacoes_entregues_em(date(2026, 6, 1), date(2026, 6, 30))

        self.assertIn(q.pk, [c.pk for c in cotacoes],
                      "o que importa é quando a fábrica entregou, não quando cotou")

    def test_of_ainda_em_producao_nao_conta(self):
        """Sem entrega não há hora consumida a atribuir — ela ainda está sendo gasta."""
        q = create_feixe_quotation(self.customer, "Em produção", created_by=self.eng)
        approve_quotation(q, self.perfil, art_number="ART-WIP")
        convert_quotation_to_of(q, created_by=self.eng)     # fica em aberta, sem completed_at

        cotacoes = cotacoes_entregues_em(date(2026, 1, 1), date(2030, 12, 31))

        self.assertEqual(len(cotacoes), 0)

    def test_cotacao_sem_of_nao_conta(self):
        """Cotação que nunca virou OF não consumiu hora de fábrica nenhuma."""
        create_feixe_quotation(self.customer, "Só cotada", created_by=self.eng)

        cotacoes = cotacoes_entregues_em(date(2026, 1, 1), date(2030, 12, 31))

        self.assertEqual(len(cotacoes), 0)

    def test_horas_do_periodo_saem_das_of_entregues(self):
        q, _of = self._of_entregue_em("Com horas", date(2026, 5, 15))

        horas = horas_estimadas_de(cotacoes_entregues_em(date(2026, 5, 1), date(2026, 5, 31)))

        self.assertGreater(horas, Decimal("0"))
        self.assertEqual(horas, horas_estimadas_de([q]))

    def test_periodo_invertido_nao_devolve_nada(self):
        self._of_entregue_em("Qualquer", date(2026, 5, 15))
        self.assertEqual(len(cotacoes_entregues_em(date(2026, 5, 31), date(2026, 5, 1))), 0)
