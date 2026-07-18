"""
Runtime de execução de aprovações (RBAC V2 M4).

Modela a EXECUÇÃO de um ApprovalWorkflow sobre uma cotação: abre um ApprovalCase,
cria uma ApprovalTask por estágio NÃO-técnico e resolve as decisões (aprovar/rejeitar).

Divisão de responsabilidade com o F10 (deliberada, para preservar 100% o gate CREA):
- O estágio TÉCNICO (is_builtin) continua sendo satisfeito pela TechnicalApproval existente
  (fluxo CREA/senha/ART) — NÃO vira task. Ele entra no `workflow_snapshot` (para ordenação
  sequencial) mas não é decidido aqui.
- Os estágios NÃO-técnicos viram tasks decididas por UMA aprovação de qualquer usuário
  qualificado (papel com a `approver_capability` do estágio). Sem quórum (V2.0).

Semântica: estágios sequenciais por `order`; um estágio só pode ser aprovado quando todos
os estágios required de `order` menor já estão satisfeitos. Snapshot do cálculo congelado no
case → editar/recalcular a cotação invalida o case (mesmo mecanismo do TechnicalApproval).
SoD (G3): o solicitante não aprova a própria, salvo se NENHUM outro usuário for qualificado
(escape auditado em metadata.self_approved).
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import ApprovalCase, ApprovalTask
from apps.audit.services import latest_snapshot_for, log_access


def _workflow_and_stages():
    from apps.access.workflow_templates import seed_workflow

    wf = seed_workflow()
    return wf, list(wf.stages.all().order_by("order", "key"))


def _stage_dict(stage):
    return {
        "key": stage.key,
        "label": stage.label,
        "order": stage.order,
        "required": stage.required,
        "approver_capability": stage.approver_capability,
        "is_builtin": stage.is_builtin,
    }


def workflow_needs_case():
    """True se o fluxo ativo tem ao menos um estágio required NÃO-técnico (senão o gate
    técnico do F10 basta e nenhum case é necessário)."""
    _wf, stages = _workflow_and_stages()
    return any(s.required and not s.is_builtin and s.approver_capability for s in stages)


@transaction.atomic
def open_case(quotation, requested_by, request=None):
    """Abre um ApprovalCase para of.convert. Invalida qualquer case OPEN anterior desta
    cotação (nova solicitação = case novo, histórico preservado). Cria tasks só p/ estágios
    não-técnicos (o técnico é gateado pela TechnicalApproval)."""
    wf, stages = _workflow_and_stages()
    snap = latest_snapshot_for(quotation)
    snap_hash = snap.snapshot_hash if snap is not None else ""

    ApprovalCase.objects.filter(
        quotation=quotation, status=ApprovalCase.STATUS_OPEN
    ).update(status=ApprovalCase.STATUS_INVALIDATED, closed_at=timezone.now())

    case = ApprovalCase.objects.create(
        quotation=quotation,
        action_type=wf.action_type,
        requested_by=requested_by,
        workflow_snapshot=[_stage_dict(s) for s in stages],
        snapshot_hash=snap_hash,
        status=ApprovalCase.STATUS_OPEN,
    )
    for s in stages:
        if s.is_builtin:
            continue  # técnico: gateado pela TechnicalApproval, não vira task
        ApprovalTask.objects.create(
            case=case, stage_key=s.key, stage_label=s.label, order=s.order,
            required=s.required, approver_capability=s.approver_capability,
            is_builtin=False,
        )
    if request is not None:
        log_access(request, "case_open", case, {
            "quotation_id": quotation.pk,
            "stages": [s.key for s in stages],
        })
    return case


def active_case(quotation):
    """O ApprovalCase OPEN mais recente da cotação (ou None)."""
    return (
        ApprovalCase.objects.filter(quotation=quotation, status=ApprovalCase.STATUS_OPEN)
        .order_by("-created_at")
        .first()
    )


def _case_is_stale(quotation, case):
    """True se o cálculo da cotação mudou desde a abertura do case (invalidação por edição)."""
    snap = latest_snapshot_for(quotation)
    if snap is None:
        return True
    return case.snapshot_hash != snap.snapshot_hash


def invalidate_stale_cases(quotation, request=None):
    """Marca INVALIDATED os cases OPEN/COMPLETED cujo snapshot divergiu (chamar no
    recompute/edição). Um case concluído cujas aprovações ficaram para um snapshot
    antigo também deixa de valer — a conversão exige aprovações do snapshot atual."""
    stale_states = [ApprovalCase.STATUS_OPEN, ApprovalCase.STATUS_COMPLETED]
    for case in ApprovalCase.objects.filter(quotation=quotation, status__in=stale_states):
        if _case_is_stale(quotation, case):
            case.status = ApprovalCase.STATUS_INVALIDATED
            case.closed_at = timezone.now()
            case.save(update_fields=["status", "closed_at", "updated_at"])
            if request is not None:
                log_access(request, "case_invalidate", case, {"quotation_id": quotation.pk})


def is_qualified(profile, task):
    """True se `profile` pode decidir `task` (papel com a capability aprovadora do estágio)."""
    if profile is None or not getattr(profile, "is_active", False):
        return False
    if not task.approver_capability:
        return False
    from apps.access.enforcement import role_can

    return role_can(profile.role, task.approver_capability)


def _other_qualified_exists(task, exclude_profile):
    """True se existe OUTRO usuário ativo qualificado para a task (base do escape de SoD)."""
    from apps.accounts.models import UserProfile

    others = UserProfile.objects.filter(is_active=True).exclude(pk=exclude_profile.pk)
    return any(is_qualified(p, task) for p in others)


def _technical_satisfied(quotation):
    snap = latest_snapshot_for(quotation)
    if snap is None:
        return False
    return quotation.technical_approvals.filter(
        revoked_at__isnull=True, calculation_snapshot_hash=snap.snapshot_hash
    ).exists()


def _stage_satisfied_snapshot(quotation, case, stage_dict):
    """Satisfação de um estágio DO SNAPSHOT do case (para checar sequência)."""
    if stage_dict.get("is_builtin"):
        return _technical_satisfied(quotation)
    return case.tasks.filter(
        stage_key=stage_dict["key"], status=ApprovalTask.STATUS_APPROVED
    ).exists()


def _earlier_required_satisfied(quotation, case, task):
    """Todos os estágios required de `order` menor que o da task estão satisfeitos?"""
    for sd in case.workflow_snapshot:
        if sd.get("required") and sd.get("order", 0) < task.order:
            if not _stage_satisfied_snapshot(quotation, case, sd):
                return False
    return True


def current_task(case, quotation=None):
    """1ª task required PENDING por ordem cujos estágios anteriores já estão satisfeitos."""
    quotation = quotation or case.quotation
    for task in case.tasks.filter(required=True, status=ApprovalTask.STATUS_PENDING).order_by("order", "id"):
        if _earlier_required_satisfied(quotation, case, task):
            return task
    return None


def _maybe_complete(case):
    """Fecha o case como COMPLETED quando todas as tasks required estão aprovadas."""
    pending = case.tasks.filter(required=True).exclude(status=ApprovalTask.STATUS_APPROVED).exists()
    if not pending:
        case.status = ApprovalCase.STATUS_COMPLETED
        case.closed_at = timezone.now()
        case.save(update_fields=["status", "closed_at", "updated_at"])


@transaction.atomic
def approve_task(quotation, task_id, approver_profile, request=None):
    """Aprova uma task não-técnica. Valida: case ativo, snapshot atual, sequência, papel
    qualificado e SoD. Retorna a task. Levanta ValidationError/PermissionDenied."""
    case = active_case(quotation)
    if case is None:
        raise ValidationError("Não há solicitação de aprovação ativa para esta cotação.")
    if _case_is_stale(quotation, case):
        invalidate_stale_cases(quotation, request=request)
        raise ValidationError("A cotação foi alterada — solicite a aprovação novamente.")

    task = case.tasks.filter(pk=task_id, status=ApprovalTask.STATUS_PENDING).first()
    if task is None:
        raise ValidationError("Estágio inválido ou já decidido.")
    if not is_qualified(approver_profile, task):
        raise PermissionDenied("Seu papel não pode aprovar este estágio.")
    if not _earlier_required_satisfied(quotation, case, task):
        raise ValidationError("Há estágios anteriores ainda não aprovados.")

    wf, _stages = _workflow_and_stages()
    self_approved = False
    if wf.self_approval_blocked and case.requested_by_id and case.requested_by_id == approver_profile.pk:
        if _other_qualified_exists(task, approver_profile):
            raise PermissionDenied(
                "Você solicitou esta aprovação; outro aprovador qualificado deve decidir."
            )
        self_approved = True  # escape de SoD auditado (nenhum outro qualificado)

    task.status = ApprovalTask.STATUS_APPROVED
    task.decided_by = approver_profile
    task.decided_at = timezone.now()
    if self_approved:
        task.metadata = {**(task.metadata or {}), "self_approved": True}
    task.save(update_fields=["status", "decided_by", "decided_at", "metadata"])
    _maybe_complete(case)

    if request is not None:
        log_access(request, "task_approve", task, {
            "quotation_id": quotation.pk, "case_id": case.pk,
            "stage_key": task.stage_key, "self_approved": self_approved,
        })
    return task


@transaction.atomic
def reject_task(quotation, task_id, approver_profile, reason, request=None):
    """Rejeita uma task (motivo obrigatório) → case REJECTED. A cotação volta editável;
    nova solicitação = case novo (histórico preservado)."""
    case = active_case(quotation)
    if case is None:
        raise ValidationError("Não há solicitação de aprovação ativa para esta cotação.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Informe o motivo da rejeição.")
    task = case.tasks.filter(pk=task_id, status=ApprovalTask.STATUS_PENDING).first()
    if task is None:
        raise ValidationError("Estágio inválido ou já decidido.")
    if not is_qualified(approver_profile, task):
        raise PermissionDenied("Seu papel não pode decidir este estágio.")

    task.status = ApprovalTask.STATUS_REJECTED
    task.decided_by = approver_profile
    task.decided_at = timezone.now()
    task.reason = reason
    task.save(update_fields=["status", "decided_by", "decided_at", "reason"])
    case.status = ApprovalCase.STATUS_REJECTED
    case.closed_at = timezone.now()
    case.save(update_fields=["status", "closed_at", "updated_at"])

    if request is not None:
        log_access(request, "task_reject", task, {
            "quotation_id": quotation.pk, "case_id": case.pk,
            "stage_key": task.stage_key, "reason": reason,
        })
    return task
