from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from apps.engineering_params.models import ProcessParameter, Rate, RateSuggestion
from apps.engineering_params import services
from apps.engineering_params.simulation import (
    simulate_process_parameter_change,
    simulate_rate_change,
)
from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role as get_user_role
from apps.audit.services import log_access

_ROLES_ALTERAM_RATE = {
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_GESTOR_COMERCIAL,
    UserProfile.ROLE_ADMIN,
}
_ROLES_EDITAM_RATE = {
    UserProfile.ROLE_ENGENHEIRO,
    UserProfile.ROLE_ADMIN,
}

_PODE_ALTERAR_RATE = require_role(*_ROLES_ALTERAM_RATE)
_PODE_EDITAR_RATE = require_role(*_ROLES_EDITAM_RATE)


def _calibration_context(active_tab):
    today = timezone.localdate()
    rates = (
        Rate.objects.filter(valid_from__lte=today)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        .order_by("operacao", "-valid_from")
    )
    process_parameters = (
        ProcessParameter.objects.filter(valid_from__lte=today)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        .order_by("operacao", "metodo", "material", "-valid_from")
    )
    pending_suggestions = RateSuggestion.objects.filter(status="pending").order_by("-created_at")
    return {
        "active_tab": active_tab,
        "rates": rates,
        "process_parameters": process_parameters,
        "pending_suggestions": pending_suggestions,
    }


@_PODE_ALTERAR_RATE
def calibration(request):
    active_tab = request.GET.get("tab") or "rates"
    if active_tab not in {"rates", "process"}:
        active_tab = "rates"
    context = _calibration_context(active_tab)
    context["can_edit_rates"] = get_user_role(request.user) in _ROLES_EDITAM_RATE
    context["can_apply_suggestions"] = get_user_role(request.user) in _ROLES_ALTERAM_RATE
    template = (
        "engineering_params/_calibration_tabs.html"
        if request.headers.get("HX-Request") == "true"
        else "engineering_params/calibration.html"
    )
    return render(request, template, context)


def _parse_rate_value(raw_value, label, allow_blank=False):
    normalized = (raw_value or "").strip().replace(",", ".")
    if not normalized:
        if allow_blank:
            return None
        raise ValueError(f"{label} é obrigatório.")
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} inválido.") from exc
    if value <= 0:
        raise ValueError(f"{label} deve ser maior que zero.")
    return value


@_PODE_EDITAR_RATE
@require_POST
@transaction.atomic
def save_rate(request, pk):
    current_rate = get_object_or_404(Rate.objects.select_for_update(), pk=pk)
    today = timezone.localdate()
    if current_rate.valid_until is not None and current_rate.valid_until < today:
        raise Http404()

    new_rate_hh = _parse_rate_value(request.POST.get("rate_hh"), "Rate HH")
    new_rate_hm = _parse_rate_value(request.POST.get("rate_hm"), "Rate HM", allow_blank=True)

    previous_payload = {
        "rate_hh": str(current_rate.rate_hh),
        "rate_hm": str(current_rate.rate_hm) if current_rate.rate_hm is not None else None,
    }
    new_payload = {
        "rate_hh": str(new_rate_hh),
        "rate_hm": str(new_rate_hm) if new_rate_hm is not None else None,
    }

    if current_rate.valid_from == today:
        current_rate.rate_hh = new_rate_hh
        current_rate.rate_hm = new_rate_hm
        current_rate.save(update_fields=["rate_hh", "rate_hm"])
        new_rate = current_rate
    else:
        current_rate.valid_until = today - timedelta(days=1)
        current_rate.save(update_fields=["valid_until"])

        new_rate = Rate.objects.create(
            operacao=current_rate.operacao,
            rate_hh=new_rate_hh,
            rate_hm=new_rate_hm,
            valid_from=today,
            valid_until=None,
        )
    log_access(
        request,
        "rate_change",
        new_rate,
        {
            "operacao": current_rate.operacao,
            "anterior": previous_payload,
            "novo": new_payload,
        },
    )

    context = _calibration_context("rates")
    context["can_edit_rates"] = True
    context["can_apply_suggestions"] = get_user_role(request.user) in _ROLES_ALTERAM_RATE
    return render(request, "engineering_params/_calibration_tabs.html", context)

@_PODE_EDITAR_RATE
@require_POST
def preview_rate_impact(request, pk):
    """Impacto simulado (EPICO 4): recota o golden case com o rate PROPOSTO e devolve o
    delta de custo/preço vs o valor vigente. NADA é persistido."""
    current_rate = get_object_or_404(Rate, pk=pk)
    error = None
    impact = None
    try:
        new_rate_hh = _parse_rate_value(request.POST.get("rate_hh"), "Rate HH")
        new_rate_hm = _parse_rate_value(request.POST.get("rate_hm"), "Rate HM", allow_blank=True)
        impact = simulate_rate_change(current_rate.operacao, rate_hh=new_rate_hh, rate_hm=new_rate_hm)
    except ValueError as exc:
        error = str(exc)

    return render(request, "engineering_params/_impact_preview.html", {
        "impact": impact,
        "error": error,
        "target_id": f"rate-impact-{current_rate.pk}",
    })


def _parse_process_parameter_value(raw_value):
    normalized = (raw_value or "").strip().replace(",", ".")
    if not normalized:
        return None
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor inválido.") from exc
    if value <= 0:
        raise ValueError("Valor deve ser maior que zero.")
    return value


@_PODE_EDITAR_RATE
@require_POST
@transaction.atomic
def save_process_parameter(request, pk):
    current_param = get_object_or_404(ProcessParameter.objects.select_for_update(), pk=pk)
    today = timezone.localdate()
    if current_param.valid_until is not None and current_param.valid_until < today:
        raise Http404()

    new_valor = _parse_process_parameter_value(request.POST.get("valor"))

    previous_payload = {"valor": str(current_param.valor) if current_param.valor is not None else None}
    new_payload = {"valor": str(new_valor) if new_valor is not None else None}

    if current_param.valid_from == today:
        current_param.valor = new_valor
        current_param.save(update_fields=["valor"])
        new_param = current_param
    else:
        current_param.valid_until = today - timedelta(days=1)
        current_param.save(update_fields=["valid_until"])

        new_param = ProcessParameter.objects.create(
            operacao=current_param.operacao,
            metodo=current_param.metodo,
            material=current_param.material,
            valor=new_valor,
            unidade=current_param.unidade,
            descricao=current_param.descricao,
            valid_from=today,
            valid_until=None,
        )
    log_access(
        request,
        "param_change",
        new_param,
        {
            "operacao": current_param.operacao,
            "metodo": current_param.metodo,
            "material": current_param.material,
            "anterior": previous_payload,
            "novo": new_payload,
        },
    )

    context = _calibration_context("process")
    context["can_edit_rates"] = True
    context["can_apply_suggestions"] = get_user_role(request.user) in _ROLES_ALTERAM_RATE
    return render(request, "engineering_params/_calibration_tabs.html", context)


@_PODE_EDITAR_RATE
@require_POST
def preview_process_parameter_impact(request, pk):
    """Impacto simulado (EPICO 4): recota o golden case com o valor PROPOSTO do
    ProcessParameter e devolve o delta de custo/preço vs o valor vigente. NADA é persistido."""
    current_param = get_object_or_404(ProcessParameter, pk=pk)
    error = None
    impact = None
    try:
        new_valor = _parse_process_parameter_value(request.POST.get("valor"))
        if new_valor is None:
            raise ValueError("Valor é obrigatório para simular o impacto.")
        impact = simulate_process_parameter_change(
            current_param.operacao, current_param.metodo, current_param.material, new_valor
        )
    except ValueError as exc:
        error = str(exc)

    return render(request, "engineering_params/_impact_preview.html", {
        "impact": impact,
        "error": error,
        "target_id": f"pp-impact-{current_param.pk}",
    })


@login_required
def suggestions_list(request):
    if request.method == 'POST' and 'refresh' in request.POST:
        if get_user_role(request.user) in _ROLES_ALTERAM_RATE:
            services.generate_suggestions()
    pending = RateSuggestion.objects.filter(status='pending').order_by('-created_at')
    accepted = RateSuggestion.objects.filter(status='accepted').order_by('-resolved_at')[:10]
    dismissed = RateSuggestion.objects.filter(status='dismissed').order_by('-resolved_at')[:5]
    return render(request, 'engineering_params/suggestions_list.html', {
        'pending': pending, 'accepted': accepted, 'dismissed': dismissed
    })

@_PODE_ALTERAR_RATE
@require_POST
def suggestion_apply(request, pk):
    s = get_object_or_404(RateSuggestion, pk=pk, status='pending')
    services.apply_suggestion(s.pk, request.user, request=request)
    return redirect('engineering_params:suggestions')


@_PODE_ALTERAR_RATE
@require_POST
def accept_rate_suggestion(request, pk):
    """Aceitar sugestão a partir da aba Taxas da calibração (EPICO 4 T5)."""
    s = get_object_or_404(RateSuggestion, pk=pk, status='pending')
    services.apply_suggestion(s.pk, request.user, request=request)
    context = _calibration_context("rates")
    context["can_edit_rates"] = get_user_role(request.user) in _ROLES_EDITAM_RATE
    context["can_apply_suggestions"] = get_user_role(request.user) in _ROLES_ALTERAM_RATE
    return render(request, "engineering_params/_calibration_tabs.html", context)

@_PODE_ALTERAR_RATE
@require_POST
def suggestion_dismiss(request, pk):
    s = get_object_or_404(RateSuggestion, pk=pk, status='pending')
    services.dismiss_suggestion(s.pk, request.user)
    return redirect('engineering_params:suggestions')
