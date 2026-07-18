from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog, ApprovalRequest, TechnicalApproval
from apps.audit.services import approve_quotation, log_access, revoke_approval
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation
from apps.production.services import is_convertible


class TechnicalApprovalTests(TenantTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=self.get_test_tenant_domain())
        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")
        self.user = User.objects.create_user(username="eng", password="123")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng PE", role="engenheiro",
            crea_number="CREA-123", crea_state="SP")
        self.client.force_login(self.user)

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

    def test_aprovacao_presencial_com_senha_correta_cria_aprovacao_e_torna_convertivel(self):
        resp = self.client.post(reverse("audit:approve_presencial", args=[self.quotation.pk]), {
            "approved_by": self.engineer.pk,
            "password": "123",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertJSONEqual(resp.content.decode(), {"ok": True, "convertible": True})
        self.assertEqual(TechnicalApproval.objects.filter(quotation=self.quotation, revoked_at__isnull=True).count(), 1)
        self.assertTrue(is_convertible(self.quotation))
        log = AccessLog.objects.filter(action="approve").latest("created_at")
        self.assertEqual(log.metadata["result"], "success")
        self.assertEqual(log.metadata["approved_by_profile_id"], self.engineer.pk)
        self.assertNotIn("password", log.metadata)

    def test_aprovacao_presencial_com_senha_errada_nega_sem_criar_aprovacao(self):
        resp = self.client.post(reverse("audit:approve_presencial", args=[self.quotation.pk]), {
            "approved_by": self.engineer.pk,
            "password": "errada",
        })

        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "Nao foi possivel validar a aprovacao.", status_code=403)
        self.assertEqual(TechnicalApproval.objects.filter(quotation=self.quotation).count(), 0)
        log = AccessLog.objects.filter(action="approve").latest("created_at")
        self.assertEqual(log.metadata["result"], "denied")
        self.assertEqual(log.metadata["reason"], "invalid_credentials")

    def test_aprovacao_presencial_sem_crea_nega(self):
        sem_crea_user = User.objects.create_user(username="eng-sem-crea", password="123")
        # Estado corrompido (CREA só com espaços): o save()/clean() do UserProfile agora
        # barra isso na criação (trait requires_crea + .strip(), RBAC V2 M1). Injetamos via
        # .update() (bypassa a validação de modelo) para exercitar o guard defensivo de
        # approve_presencial, que continua negando CREA em branco em runtime.
        sem_crea = UserProfile.objects.create(
            user=sem_crea_user,
            full_name="Eng Sem CREA",
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="SP-000",
            crea_state="SP",
        )
        UserProfile.objects.filter(pk=sem_crea.pk).update(crea_number="   ")
        sem_crea.refresh_from_db()

        resp = self.client.post(reverse("audit:approve_presencial", args=[self.quotation.pk]), {
            "approved_by": sem_crea.pk,
            "password": "123",
        })

        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "Nao foi possivel validar a aprovacao.", status_code=403)
        self.assertEqual(TechnicalApproval.objects.filter(quotation=self.quotation).count(), 0)
        log = AccessLog.objects.filter(action="approve").latest("created_at")
        self.assertEqual(log.metadata["result"], "denied")
        self.assertEqual(log.metadata["reason"], "invalid_approver")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_solicitar_aprovacao_remota_registra_pendencia_e_envia_email(self):
        gestor_user = User.objects.create_user(username="gestor", email="gestor@example.com")
        UserProfile.objects.create(
            user=gestor_user,
            full_name="Gestor Comercial",
            role=UserProfile.ROLE_GESTOR_COMERCIAL,
        )

        resp = self.client.post(reverse("audit:request_remote", args=[self.quotation.pk]), {
            "notes": "Favor avaliar ainda hoje.",
        })

        self.assertEqual(resp.status_code, 302)
        pending = ApprovalRequest.objects.get(quotation=self.quotation, status=ApprovalRequest.STATUS_PENDING)
        self.assertEqual(pending.requested_by, self.user.profile)
        self.assertEqual(pending.request_type, ApprovalRequest.TYPE_REMOTE)
        self.assertEqual(pending.notes, "Favor avaliar ainda hoje.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["gestor@example.com"])
        self.assertIn(self.quotation.number, mail.outbox[0].subject)
        self.assertTrue(AccessLog.objects.filter(action="approve", metadata__result="remote_requested").exists())


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
