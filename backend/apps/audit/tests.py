from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog, TechnicalApproval
from apps.audit.services import approve_quotation, log_access, revoke_approval
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class TechnicalApprovalTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")
        self.user = User.objects.create_user(username="eng")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng PE", role="engenheiro",
            crea_number="CREA-123", crea_state="SP")

    def _request(self):
        request = RequestFactory().post("/audit/", REMOTE_ADDR="127.0.0.1")
        request.user = self.user
        return request

    def test_approve_quotation_vincula_snapshot_atual(self):
        approval = approve_quotation(self.quotation, self.engineer, art_number="ART-1")
        self.assertEqual(approval.crea_number, "CREA-123")
        self.assertEqual(approval.art_number, "ART-1")
        self.assertEqual(approval.calculation_snapshot_hash, self.quotation.snapshots.first().snapshot_hash)
        self.assertTrue(approval.is_active)


    def test_approve_quotation_registra_access_log_quando_request_informado(self):
        approval = approve_quotation(self.quotation, self.engineer, request=self._request())
        self.assertTrue(AccessLog.objects.filter(
            action="approve", resource_type="TechnicalApproval",
            resource_id=str(approval.pk)).exists())

    def test_approval_exige_engenheiro_com_crea(self):
        user = User.objects.create_user(username="orc")
        profile = UserProfile.objects.create(user=user, full_name="Orc", role="orcamentista")
        with self.assertRaises(ValidationError):
            approve_quotation(self.quotation, profile)

    def test_revoke_approval_e_logico(self):
        approval = approve_quotation(self.quotation, self.engineer)
        revoke_approval(approval, self.engineer, request=self._request())
        approval.refresh_from_db()
        self.assertFalse(approval.is_active)
        self.assertEqual(approval.revoked_by, self.engineer)
        self.assertEqual(TechnicalApproval.objects.count(), 1)
        self.assertTrue(AccessLog.objects.filter(action="revoke", resource_id=str(approval.pk)).exists())

    def test_approval_falha_sem_snapshot(self):
        self.quotation.snapshots.all().delete()
        with self.assertRaises(ValidationError):
            approve_quotation(self.quotation, self.engineer)


class AccessLogTests(TenantTestCase):
    def test_log_access_registra_request(self):
        user = User.objects.create_user(username="orc")
        customer = Customer.objects.create(company_name="ACME")
        quotation = create_feixe_quotation(customer, "Feixe")
        request = RequestFactory().get("/cotacoes/1/", HTTP_USER_AGENT="pytest", REMOTE_ADDR="127.0.0.1")
        request.user = user

        log = log_access(request, "view", quotation, {"source": "test"})

        self.assertEqual(log.user, user)
        self.assertEqual(log.action, "view")
        self.assertEqual(log.resource_type, "Quotation")
        self.assertEqual(log.resource_id, str(quotation.pk))
        self.assertEqual(log.ip_address, "127.0.0.1")
        self.assertEqual(log.metadata["source"], "test")
        self.assertEqual(AccessLog.objects.count(), 1)
