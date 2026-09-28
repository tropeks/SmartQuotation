"""
Ordem 007 — P7: não se revisa uma cotação cujo número já tem Ordem de Fabricação ativa
(não cancelada).
"""
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class RevisaoBloqueiaComOfAtivaTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME P7")

    def _aprova_e_converte(self, q):
        from apps.accounts.models import UserProfile
        from apps.audit.services import approve_quotation
        from apps.production.services import convert_quotation_to_of
        from django.contrib.auth.models import User

        user = User.objects.create_user(username=f"eng-p7-{q.pk}")
        engineer = UserProfile.objects.create(
            user=user, full_name="Eng P7", role="engenheiro",
            crea_number="CREA-P7", crea_state="SP")
        approve_quotation(q, engineer)
        return convert_quotation_to_of(q, created_by=user)

    def test_revise_feixe_recusa_se_numero_ja_tem_of(self):
        from apps.quotations.adapter import revise_feixe
        from apps.quotations.services import QuotationHasProductionOrderError

        q = create_feixe_quotation(self.customer, "Feixe P7")
        self._aprova_e_converte(q)
        with self.assertRaises(QuotationHasProductionOrderError):
            revise_feixe(q, created_by=None)

    def test_of_cancelada_nao_bloqueia_a_revisao(self):
        """Uma OF CANCELADA não é "ativa" — não deve bloquear a revisão."""
        from apps.production.models import STATUS_CANCELADA
        from apps.quotations.adapter import revise_feixe

        q = create_feixe_quotation(self.customer, "Feixe P7b")
        of = self._aprova_e_converte(q)
        of.status = STATUS_CANCELADA
        of.save(update_fields=["status"])
        revisada = revise_feixe(q, created_by=None)
        self.assertEqual(revisada.number, q.number)
        self.assertEqual(revisada.revision, 1)


class RevisaoCompleteBloqueiaComOfAtivaTests(TenantTestCase):
    """P7 espelhado para `revise_complete` (permutador completo) — NIT da revisão do
    Diretor: só havia cobertura de P7 para `revise_feixe`."""

    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME P7 Complete")

    def _cotacao_beu(self):
        from apps.quotations.adapter import persist_complete
        from pricing_engine.permutador_quote import quote_completo

        resultado = quote_completo("BEU")
        return persist_complete(
            self.customer, "BEU", {"designacao": "BEU", "n_tubos": 68}, resultado,
            title="BEU P7")

    def _aprova_e_converte(self, q):
        from apps.accounts.models import UserProfile
        from apps.audit.services import approve_quotation
        from apps.production.services import convert_quotation_to_of
        from django.contrib.auth.models import User

        user = User.objects.create_user(username=f"eng-p7c-{q.pk}")
        engineer = UserProfile.objects.create(
            user=user, full_name="Eng P7 Complete", role="engenheiro",
            crea_number="CREA-P7C", crea_state="SP")
        approve_quotation(q, engineer)
        return convert_quotation_to_of(q, created_by=user)

    def test_revise_complete_recusa_se_numero_ja_tem_of(self):
        from apps.quotations.adapter import revise_complete
        from apps.quotations.services import QuotationHasProductionOrderError

        q = self._cotacao_beu()
        self._aprova_e_converte(q)
        with self.assertRaises(QuotationHasProductionOrderError):
            revise_complete(q, created_by=None)

    def test_of_cancelada_nao_bloqueia_a_revisao_complete(self):
        from apps.production.models import STATUS_CANCELADA
        from apps.quotations.adapter import revise_complete

        q = self._cotacao_beu()
        of = self._aprova_e_converte(q)
        of.status = STATUS_CANCELADA
        of.save(update_fields=["status"])
        revisada = revise_complete(q, created_by=None)
        self.assertEqual(revisada.number, q.number)
        self.assertEqual(revisada.revision, 1)
