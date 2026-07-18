from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.access.enforcement import require_capability, user_can
from apps.audit import approvals
from apps.audit.models import ApprovalCase, ApprovalTask
from apps.audit.services import approve_presencial, request_remote_approval
from apps.production.services import is_convertible
from apps.quotations.models import Quotation

_WRITE_ROLES = (
    UserProfile.ROLE_ORCAMENTISTA,
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
)

_READ_ROLES = _WRITE_ROLES


@require_POST
@require_capability("approval.request_remote")
def request_remote(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    request_remote_approval(
        quotation,
        request.user.profile,
        notes=request.POST.get("notes", ""),
        request=request,
    )
    messages.success(request, "Solicitação de aprovação remota registrada.")
    return redirect("quotations:detail", pk=quotation.pk)


@require_POST
@require_capability("approval.request_presencial")
def approve_presencial_view(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    approver_profile = get_object_or_404(UserProfile.objects.select_related("user"), pk=request.POST.get("approved_by"))
    try:
        approve_presencial(
            quotation,
            approver_profile,
            request.POST.get("password", ""),
            request=request,
            notes=request.POST.get("notes", ""),
        )
    except ValidationError:
        return HttpResponse("Nao foi possivel validar a aprovacao.", status=403)
    if request.headers.get("HX-Request") == "true":
        return HttpResponse("Aprovacao confirmada.")
    return JsonResponse({"ok": True, "convertible": is_convertible(quotation)})


@require_GET
@require_capability("approval.panel_read")
def convertibility_panel(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    return render(
        request,
        "quotations/_convert_action.html",
        {
            "q": quotation,
            "has_active_of": quotation.ordens_fabricacao.exclude(status="cancelada").exists(),
            "is_convertible": is_convertible(quotation),
            "can_convert": user_can(request.user, "of.convert"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# RBAC V2 M5 — Inbox "Aprovações" + badge. Dirige o runtime do M4 via HTTP.
# ─────────────────────────────────────────────────────────────────────────────

def _my_profile(request):
    return getattr(request.user, "profile", None)


@require_POST
@require_capability("approval.request_remote")
def request_approval(request, pk):
    """Abre um ApprovalCase para a cotação (fluxo multi-estágio) e notifica os aprovadores
    do estágio corrente. Se o fluxo é só-técnica, não há case — mantém o fluxo CREA do F10."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if not approvals.workflow_needs_case():
        messages.info(request, "Este fluxo usa apenas a aprovação técnica (CREA).")
        return redirect("quotations:detail", pk=quotation.pk)
    case = approvals.open_case(quotation, _my_profile(request), request=request)
    approvals.notify_current_stage_approvers(case, request=request)
    messages.success(request, "Solicitação de aprovação aberta.")
    return redirect("quotations:detail", pk=quotation.pk)


def _task_card(task):
    q = task.case.quotation
    return {
        "task": task,
        "case": task.case,
        "quotation": q,
        "number": q.number,
        "title": q.title,
        "customer": getattr(q.customer, "company_name", ""),
        "value": q.preco_com_impostos,
        "stage_label": task.stage_label,
        "requested_by": getattr(task.case.requested_by, "full_name", "—"),
        "created_at": task.case.created_at,
    }


@login_required
@require_capability("approval.panel_read")
def inbox(request):
    """Inbox de aprovações — abas 'A aprovar' (meu papel decide) e 'Minhas solicitações'."""
    profile = _my_profile(request)
    to_approve = [_task_card(t) for t in approvals.inbox_tasks_for(profile)]
    my_cases = approvals.cases_requested_by(profile)
    return render(request, "audit/inbox.html", {
        "to_approve": to_approve,
        "my_cases": my_cases,
        "tab": request.GET.get("tab", "approve"),
    })


@login_required
@require_capability("approval.panel_read")
def inbox_badge(request):
    """Parcial do badge (poller HTMX) — nº de pendências do MEU papel."""
    count = approvals.inbox_count_for_role_cached(user_role(request.user))
    return render(request, "audit/_inbox_badge.html", {"count": count})


@require_POST
@require_capability("approval.panel_read")
def approve_task(request, task_id):
    """Aprova a task não-técnica do estágio corrente (aba 'A aprovar')."""
    task = get_object_or_404(ApprovalTask.objects.select_related("case__quotation"), pk=task_id)
    try:
        approvals.approve_task(task.case.quotation, task.pk, _my_profile(request), request=request)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, getattr(exc, "message", str(exc)))
        return redirect("audit:inbox")
    messages.success(request, "Estágio aprovado.")
    return redirect("audit:inbox")


@require_POST
@require_capability("approval.panel_read")
def reject_task(request, task_id):
    """Rejeita a task do estágio corrente (motivo obrigatório) → case rejeitado."""
    task = get_object_or_404(ApprovalTask.objects.select_related("case__quotation"), pk=task_id)
    try:
        approvals.reject_task(
            task.case.quotation, task.pk, _my_profile(request),
            reason=request.POST.get("reason", ""), request=request,
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, getattr(exc, "message", str(exc)))
        return redirect("audit:inbox")
    messages.success(request, "Estágio rejeitado.")
    return redirect("audit:inbox")
