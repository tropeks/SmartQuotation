"""
Testes do runtime de execução de aprovações (RBAC V2 M4): ApprovalCase/ApprovalTask,
integração com is_convertible, sequência de estágios, SoD e invalidação por edição.

O estágio técnico (CREA) segue via TechnicalApproval (F10); os não-técnicos viram tasks
decididas por papel qualificado. Fixture: fluxo Técnica + Comercial (commercial_sign = {G, A}).
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.matrix import seed_access_matrix
from apps.access.models import ApprovalStage
from apps.access.workflow_templates import seed_workflow
from apps.accounts.models import UserProfile
from apps.audit import approvals
from apps.audit.models import ApprovalCase, ApprovalTask
from apps.audit.services import approve_quotation, revoke_approval
from apps.production import services as prod
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class ApprovalRuntimeBase(TestCase):
    def setUp(self):
        cache.clear()
        seed_access_matrix()
        self.wf = seed_workflow()
        # Fluxo Técnica + Comercial: adiciona o estágio comercial (approver = commercial_sign).
        ApprovalStage.objects.create(
            workflow=self.wf, key="commercial", label="Aprovação comercial", order=20,
            required=True, approver_capability="approval.commercial_sign", is_builtin=False,
        )
        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")

        self.eng = self._profile("eng", UserProfile.ROLE_ENGENHEIRO, crea="CREA-1")
        self.gestor = self._profile("gestor", UserProfile.ROLE_GESTOR_COMERCIAL)
        self.gestor2 = self._profile("gestor2", UserProfile.ROLE_GESTOR_COMERCIAL)
        self.orca = self._profile("orca", UserProfile.ROLE_ORCAMENTISTA)

    def _profile(self, username, role, crea=""):
        u = User.objects.create_user(username=username, password="x")
        return UserProfile.objects.create(
            user=u, full_name=username, role=role, crea_number=crea,
            crea_state="SP" if crea else "",
        )

    def _commercial_task(self, case):
        return case.tasks.get(stage_key="commercial")


class OpenCaseTests(ApprovalRuntimeBase):
    def test_open_case_cria_tasks_so_nao_tecnicas(self):
        case = approvals.open_case(self.quotation, self.eng)
        self.assertEqual(case.status, ApprovalCase.STATUS_OPEN)
        keys = list(case.tasks.values_list("stage_key", flat=True))
        self.assertEqual(keys, ["commercial"])  # técnico não vira task
        # o snapshot do workflow inclui o técnico (para ordenação)
        snap_keys = {s["key"] for s in case.workflow_snapshot}
        self.assertIn("technical", snap_keys)
        self.assertIn("commercial", snap_keys)

    def test_reabrir_invalida_case_anterior(self):
        c1 = approvals.open_case(self.quotation, self.eng)
        c2 = approvals.open_case(self.quotation, self.eng)
        c1.refresh_from_db()
        self.assertEqual(c1.status, ApprovalCase.STATUS_INVALIDATED)
        self.assertEqual(c2.status, ApprovalCase.STATUS_OPEN)


class ConvertibilityTests(ApprovalRuntimeBase):
    def test_fluxo_completo_tecnica_depois_comercial(self):
        # sem nada -> não convertível
        self.assertFalse(prod.is_convertible(self.quotation))
        # aprovação técnica satisfaz o estágio técnico, mas comercial ainda falta
        approve_quotation(self.quotation, self.eng)
        self.assertFalse(prod.is_convertible(self.quotation))
        # abre case; comercial pendente -> ainda não
        case = approvals.open_case(self.quotation, self.eng)
        self.assertFalse(prod.is_convertible(self.quotation))
        # gestor aprova comercial -> case completo -> convertível
        task = self._commercial_task(case)
        approvals.approve_task(self.quotation, task.pk, self.gestor)
        case.refresh_from_db()
        self.assertEqual(case.status, ApprovalCase.STATUS_COMPLETED)
        self.assertTrue(prod.is_convertible(self.quotation))

    def test_orcamentista_nao_qualificado(self):
        approve_quotation(self.quotation, self.eng)
        case = approvals.open_case(self.quotation, self.eng)
        task = self._commercial_task(case)
        with self.assertRaises(PermissionDenied):
            approvals.approve_task(self.quotation, task.pk, self.orca)

    def test_sequencia_comercial_bloqueado_antes_da_tecnica(self):
        # sem aprovação técnica, aprovar comercial deve falhar (estágio anterior não satisfeito)
        case = approvals.open_case(self.quotation, self.eng)
        task = self._commercial_task(case)
        with self.assertRaises(ValidationError):
            approvals.approve_task(self.quotation, task.pk, self.gestor)


class RejectionTests(ApprovalRuntimeBase):
    def test_rejeicao_exige_motivo_e_fecha_case(self):
        approve_quotation(self.quotation, self.eng)
        case = approvals.open_case(self.quotation, self.eng)
        task = self._commercial_task(case)
        with self.assertRaises(ValidationError):
            approvals.reject_task(self.quotation, task.pk, self.gestor, reason="")
        approvals.reject_task(self.quotation, task.pk, self.gestor, reason="preço baixo")
        case.refresh_from_db()
        self.assertEqual(case.status, ApprovalCase.STATUS_REJECTED)
        self.assertFalse(prod.is_convertible(self.quotation))


class SoDTests(ApprovalRuntimeBase):
    def test_solicitante_nao_aprova_a_propria_com_outro_qualificado(self):
        approve_quotation(self.quotation, self.eng)
        # gestor solicita E tenta aprovar; existe gestor2 qualificado -> bloqueado
        case = approvals.open_case(self.quotation, self.gestor)
        task = self._commercial_task(case)
        with self.assertRaises(PermissionDenied):
            approvals.approve_task(self.quotation, task.pk, self.gestor)

    def test_escape_quando_ninguem_mais_qualificado(self):
        approve_quotation(self.quotation, self.eng)
        # remove os demais qualificados (gestor2 e o admin não existe aqui) -> escape auditado
        self.gestor2.is_active = False
        self.gestor2.save(update_fields=["is_active"])
        case = approvals.open_case(self.quotation, self.gestor)
        task = self._commercial_task(case)
        approvals.approve_task(self.quotation, task.pk, self.gestor)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTask.STATUS_APPROVED)
        self.assertTrue(task.metadata.get("self_approved"))

    def test_sod_desligado_permite_auto_aprovacao(self):
        approve_quotation(self.quotation, self.eng)
        self.wf.self_approval_blocked = False
        self.wf.save(update_fields=["self_approval_blocked"])
        case = approvals.open_case(self.quotation, self.gestor)
        task = self._commercial_task(case)
        approvals.approve_task(self.quotation, task.pk, self.gestor)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTask.STATUS_APPROVED)
        self.assertFalse(task.metadata.get("self_approved"))


class TechnicalApprovalSatisfiedTests(ApprovalRuntimeBase):
    """API pública `approvals.technical_approval_satisfied` (ex-`_technical_satisfied`).

    Consumida por `open_case`/`current_task` (gate do estágio técnico built-in) e por
    `apps.quotations.views._selo` (estado do selo de confiança da tela de detalhe).
    """

    def test_sem_aprovacao_nenhuma_e_nao_satisfeito(self):
        self.assertFalse(approvals.technical_approval_satisfied(self.quotation))

    def test_aprovacao_cobrindo_snapshot_vigente_e_satisfeito(self):
        approve_quotation(self.quotation, self.eng)
        self.assertTrue(approvals.technical_approval_satisfied(self.quotation))

    def test_aprovacao_divergente_apos_novo_snapshot_nao_e_satisfeito(self):
        from apps.quotations.models import CalculationSnapshot

        approve_quotation(self.quotation, self.eng)
        self.assertTrue(approvals.technical_approval_satisfied(self.quotation))
        CalculationSnapshot.objects.create(
            quotation=self.quotation, snapshot_hash="HASH-EDITADO",
            inputs={}, outputs={}, engine_version="x", standard_refs=[],
        )
        self.assertFalse(approvals.technical_approval_satisfied(self.quotation))

    def test_aprovacao_revogada_nao_e_satisfeito(self):
        approval = approve_quotation(self.quotation, self.eng)
        self.assertTrue(approvals.technical_approval_satisfied(self.quotation))
        revoke_approval(approval, self.eng)
        self.assertFalse(approvals.technical_approval_satisfied(self.quotation))

    def test_usado_como_gate_do_estagio_tecnico_no_current_task(self):
        """Confirma que open_case/current_task consultam a MESMA função pública."""
        case = approvals.open_case(self.quotation, self.eng)
        task = self._commercial_task(case)
        # sem aprovação técnica -> estágio anterior (built-in) não satisfeito -> bloqueado
        with self.assertRaises(ValidationError):
            approvals.approve_task(self.quotation, task.pk, self.gestor)
        approve_quotation(self.quotation, self.eng)
        self.assertTrue(approvals.technical_approval_satisfied(self.quotation))
        # agora o estágio comercial pode ser decidido
        approvals.approve_task(self.quotation, task.pk, self.gestor)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTask.STATUS_APPROVED)


class InvalidationTests(ApprovalRuntimeBase):
    def test_recalculo_invalida_case_e_bloqueia_conversao(self):
        from apps.quotations.models import CalculationSnapshot

        approve_quotation(self.quotation, self.eng)
        case = approvals.open_case(self.quotation, self.eng)
        task = self._commercial_task(case)
        approvals.approve_task(self.quotation, task.pk, self.gestor)
        self.assertTrue(prod.is_convertible(self.quotation))
        # Edição/recalculo com conteúdo diferente -> novo snapshot_hash divergente.
        CalculationSnapshot.objects.create(
            quotation=self.quotation, snapshot_hash="HASH-EDITADO",
            inputs={}, outputs={}, engine_version="x", standard_refs=[],
        )
        approvals.invalidate_stale_cases(self.quotation)
        case.refresh_from_db()
        self.assertEqual(case.status, ApprovalCase.STATUS_INVALIDATED)
        # técnico também cai (snapshot mudou) -> não convertível de qualquer forma
        self.assertFalse(prod.is_convertible(self.quotation))
