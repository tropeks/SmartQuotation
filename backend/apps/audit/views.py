from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role
from apps.access.enforcement import require_capability, user_can
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
