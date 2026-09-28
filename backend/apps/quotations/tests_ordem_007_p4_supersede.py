"""
Ordem 007 — P4: criar uma revisão marca `superseded` as propostas draft/ready das
revisões ANTERIORES do mesmo número; as já enviadas ('sent') ficam como estão.
"""
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class SupersedePropostasAnterioresTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME P4")

    def test_revisar_marca_draft_e_ready_como_superseded_mas_preserva_sent(self):
        from apps.proposals.models import ProposalTemplate
        from apps.proposals import services as proposal_services
        from apps.quotations.adapter import revise_feixe

        orig = create_feixe_quotation(self.customer, "Feixe P4")
        tpl = ProposalTemplate.objects.create(name="Padrão P4", is_default=True)
        p_draft = proposal_services.create_proposal(orig, tpl)
        p_ready = proposal_services.create_proposal(orig, tpl)
        p_ready.status = "ready"
        p_ready.save(update_fields=["status"])
        p_sent = proposal_services.create_proposal(orig, tpl)
        p_sent.status = "sent"
        p_sent.save(update_fields=["status"])

        revise_feixe(orig, created_by=None)

        p_draft.refresh_from_db()
        p_ready.refresh_from_db()
        p_sent.refresh_from_db()
        self.assertEqual(p_draft.status, "superseded")
        self.assertEqual(p_ready.status, "superseded")
        self.assertEqual(p_sent.status, "sent")   # já saiu — não se mexe
