"""
Testes do inbox de aprovações (RBAC V2 M5): endpoints HTTP que dirigem o runtime do M4
(solicitar, aprovar, rejeitar), a página de inbox, o badge por papel e o e-mail p/ os
aprovadores do estágio corrente (fecha o resto do #86).
"""
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.matrix import seed_access_matrix
from apps.access.models import ApprovalStage
from apps.access.workflow_templates import seed_workflow
from apps.accounts.models import UserProfile
from apps.audit import approvals
from apps.audit.models import ApprovalCase, ApprovalTask
from apps.audit.services import approve_quotation
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class InboxBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        seed_access_matrix()
        self.wf = seed_workflow()
        ApprovalStage.objects.create(
            workflow=self.wf, key="commercial", label="Aprovação comercial", order=20,
            required=True, approver_capability="approval.commercial_sign", is_builtin=False,
        )
        self.customer = Customer.objects.create(company_name="ACME")
        self.q = create_feixe_quotation(self.customer, "Feixe")
        self.eng = self._profile("eng", UserProfile.ROLE_ENGENHEIRO, crea="CREA-1", email="eng@x.com")
        self.gestor = self._profile("gestor", UserProfile.ROLE_GESTOR_COMERCIAL, email="g@x.com")

    def _profile(self, username, role, crea="", email=""):
        u = User.objects.create_user(username=username, password="x", email=email)
        return UserProfile.objects.create(
            user=u, full_name=username, role=role, crea_number=crea,
            crea_state="SP" if crea else "",
        )


class RequestApprovalTests(InboxBase):
    def test_solicitar_abre_case(self):
        self.client.force_login(self.eng.user)
        resp = self.client.post(f"/cotacoes/{self.q.pk}/aprovacoes/solicitar/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ApprovalCase.objects.filter(quotation=self.q, status=ApprovalCase.STATUS_OPEN).exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_solicitar_notifica_aprovadores_do_estagio(self):
        # técnica satisfeita para o estágio corrente virar o comercial
        approve_quotation(self.q, self.eng)
        self.client.force_login(self.eng.user)
        self.client.post(f"/cotacoes/{self.q.pk}/aprovacoes/solicitar/")
        # o estágio corrente é o comercial -> notifica quem tem commercial_sign (gestor)
        self.assertTrue(any("g@x.com" in m.to for m in mail.outbox))


class InboxViewTests(InboxBase):
    def _open_and_tech(self):
        approve_quotation(self.q, self.eng)
        return approvals.open_case(self.q, self.eng)

    def test_inbox_mostra_task_para_papel_qualificado(self):
        self._open_and_tech()
        self.client.force_login(self.gestor.user)
        resp = self.client.get("/aprovacoes/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.q.number)
        self.assertContains(resp, "Aprovação comercial")

    def test_inbox_vazio_para_papel_nao_qualificado(self):
        self._open_and_tech()
        self.client.force_login(self.eng.user)  # engenheiro não tem commercial_sign
        resp = self.client.get("/aprovacoes/")
        self.assertNotContains(resp, "Aprovação comercial")

    def test_aprovar_via_http(self):
        case = self._open_and_tech()
        task = case.tasks.get(stage_key="commercial")
        self.client.force_login(self.gestor.user)
        resp = self.client.post(f"/aprovacoes/task/{task.pk}/aprovar/")
        self.assertEqual(resp.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTask.STATUS_APPROVED)

    def test_rejeitar_via_http_exige_motivo(self):
        case = self._open_and_tech()
        task = case.tasks.get(stage_key="commercial")
        self.client.force_login(self.gestor.user)
        self.client.post(f"/aprovacoes/task/{task.pk}/rejeitar/", {"reason": "fora de escopo"})
        case.refresh_from_db()
        self.assertEqual(case.status, ApprovalCase.STATUS_REJECTED)


class BadgeTests(InboxBase):
    def test_contagem_por_papel(self):
        approve_quotation(self.q, self.eng)
        approvals.open_case(self.q, self.eng)
        # gestor (commercial_sign) tem 1 pendência; engenheiro tem 0
        self.assertEqual(approvals.inbox_count_for_role(UserProfile.ROLE_GESTOR_COMERCIAL), 1)
        self.assertEqual(approvals.inbox_count_for_role(UserProfile.ROLE_ENGENHEIRO), 0)

    def test_badge_endpoint(self):
        approve_quotation(self.q, self.eng)
        approvals.open_case(self.q, self.eng)
        self.client.force_login(self.gestor.user)
        resp = self.client.get("/aprovacoes/badge/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1")
