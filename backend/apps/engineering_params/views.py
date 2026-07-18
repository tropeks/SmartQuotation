from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from apps.engineering_params.models import (
    ProcessParameter, Rate, RateSuggestion, TenantParamConfig,
    _default_perda_por_familia, _default_setup_frac,
)
from apps.engineering_params import services
from apps.engineering_params.simulation import (
    simulate_process_parameter_change,
    simulate_rate_change,
)
from apps.accounts.models import UserProfile
from apps.accounts.rbac import require_role, user_role as get_user_role
from apps.access.enforcement import require_capability, user_can
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

_PODE_ALTERAR_RATE = require_capability("rate.change")
_PODE_EDITAR_RATE = require_capability("rate.edit")


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
    context["can_edit_rates"] = user_can(request.user, "rate.edit")
    context["can_apply_suggestions"] = user_can(request.user, "rate.change")
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
    context["can_apply_suggestions"] = user_can(request.user, "rate.change")
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
    context["can_apply_suggestions"] = user_can(request.user, "rate.change")
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
        if user_can(request.user, "rate.change"):
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
    context["can_edit_rates"] = user_can(request.user, "rate.edit")
    context["can_apply_suggestions"] = user_can(request.user, "rate.change")
    return render(request, "engineering_params/_calibration_tabs.html", context)

@_PODE_ALTERAR_RATE
@require_POST
def suggestion_dismiss(request, pk):
    s = get_object_or_404(RateSuggestion, pk=pk, status='pending')
    services.dismiss_suggestion(s.pk, request.user)
    return redirect('engineering_params:suggestions')


# ── Config de Engenharia V2 / F1 (Bloco C): knobs configuráveis (scrap por família + setup
# por parâmetro). Página própria, mesmo padrão da Calibração (POST cru + HTMX + log_access).
# Faixa segura ±50% do default em modo WARN (avisa, não bloqueia — F1). Gate: rate.edit.

_KNOB_WARN_FRAC = 0.5  # faixa segura = default × [1-0.5, 1+0.5] (±50%); fora → aviso, não bloqueia


def _knob_rows(values, defaults):
    """Linhas (key, value, default, faixa, fora_da_faixa) p/ a UI. 'fora' só avisa (warn)."""
    rows = []
    for key in sorted(values):
        try:
            val = float(values[key])
        except (TypeError, ValueError):
            continue
        dflt = defaults.get(key)
        lo = hi = None
        fora = False
        if dflt:
            lo = round(dflt * (1 - _KNOB_WARN_FRAC), 4)
            hi = round(dflt * (1 + _KNOB_WARN_FRAC), 4)
            fora = val < lo or val > hi
        rows.append({"key": key, "value": val, "default": dflt, "lo": lo, "hi": hi, "fora": fora})
    return rows


def _knobs_context():
    cfg = TenantParamConfig.get_solo()
    return {
        "perda_rows": _knob_rows(cfg.perda_por_familia or {}, _default_perda_por_familia()),
        "setup_rows": _knob_rows(cfg.setup_frac or {}, _default_setup_frac()),
    }


@_PODE_ALTERAR_RATE
def knobs(request):
    context = _knobs_context()
    context["can_edit_knobs"] = user_can(request.user, "rate.edit")
    template = (
        "engineering_params/_knobs_form.html"
        if request.headers.get("HX-Request") == "true"
        else "engineering_params/knobs.html"
    )
    return render(request, template, context)


def _parse_factor(raw_value):
    """Fator > 0 (aceita vírgula). Vazio → None (não altera). Inválido → ValueError."""
    normalized = (raw_value or "").strip().replace(",", ".")
    if not normalized:
        return None
    try:
        value = float(Decimal(normalized))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor inválido.") from exc
    if value <= 0:
        raise ValueError("Valor deve ser maior que zero.")
    return value


@_PODE_EDITAR_RATE
@require_POST
@transaction.atomic
def save_knobs(request):
    """Salva os knobs (perda_por_familia + setup_frac) do TenantParamConfig e audita o diff.
    Só edita chaves JÁ existentes (a UI não cria/apaga famílias/parâmetros). Entrada inválida
    ou vazia mantém o valor atual. Fora da faixa ±50% NÃO bloqueia (F1 = warn)."""
    TenantParamConfig.get_solo()  # garante a linha singleton
    cfg = TenantParamConfig.objects.select_for_update().get(pk=1)
    before_perda = dict(cfg.perda_por_familia or {})
    before_setup = dict(cfg.setup_frac or {})

    def _apply(prefix, current):
        novo = dict(current)
        for key in current:
            try:
                parsed = _parse_factor(request.POST.get(f"{prefix}__{key}"))
            except ValueError:
                continue  # mantém o valor atual em entrada inválida
            if parsed is not None:
                novo[key] = parsed
        return novo

    cfg.perda_por_familia = _apply("perda", before_perda)
    cfg.setup_frac = _apply("setup", before_setup)
    cfg.save(update_fields=["perda_por_familia", "setup_frac"])

    if cfg.perda_por_familia != before_perda or cfg.setup_frac != before_setup:
        log_access(request, "param_change", cfg, {
            "knob": "config_engenharia_v2",
            "anterior": {"perda_por_familia": before_perda, "setup_frac": before_setup},
            "novo": {"perda_por_familia": cfg.perda_por_familia, "setup_frac": cfg.setup_frac},
        })

    context = _knobs_context()
    context["can_edit_knobs"] = True
    context["saved"] = True
    return render(request, "engineering_params/_knobs_form.html", context)
