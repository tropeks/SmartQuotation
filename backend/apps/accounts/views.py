"""
Views de sessão (session auth, sem JWT).
- login_view: autentica por username OU e-mail; HTMX-friendly (partial em erro).
- logout_view: encerra a sessão e volta ao login.
- dashboard_view: dashboard executivo protegido por login.
"""
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import LoginForm
from apps.accounts.rbac import has_tenant_membership
from apps.audit.models import TechnicalApproval
from apps.quotations.models import Quotation


def _resolve_username(identifier):
    """Aceita login por e-mail: traduz e-mail -> username quando possível."""
    if identifier and "@" in identifier:
        match = User.objects.filter(email__iexact=identifier).first()
        if match is not None:
            return match.username
    return identifier


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Renderiza/processa o formulário de login. Em erro HTMX, devolve só o form."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = _resolve_username(form.cleaned_data["identifier"])
        user = authenticate(
            request, username=username, password=form.cleaned_data["password"]
        )
        # has_tenant_membership: o user precisa ter UserProfile no schema (tenant) atual.
        # Sem isso, um usuário de outro tenant autenticaria aqui (auth.User é global).
        # Mesma mensagem genérica para não revelar se o usuário existe noutro tenant.
        if user is not None and user.is_active and has_tenant_membership(user):
            login(request, user)
            # Sob HTMX o 302 seria seguido pela XHR e o dashboard cairia dentro do
            # #login-form. HX-Redirect faz o htmx navegar a página de verdade.
            if _is_htmx(request):
                resp = HttpResponse(status=204)
                resp["HX-Redirect"] = reverse("dashboard")
                return resp
            return redirect("dashboard")
        form.add_error(None, "Credenciais inválidas.")

    template = "accounts/_login_form.html" if _is_htmx(request) else "accounts/login.html"
    status = 400 if (request.method == "POST" and form.errors) else 200
    return render(request, template, {"form": form}, status=status)


@require_http_methods(["POST", "GET"])
def logout_view(request):
    """Encerra a sessão e redireciona para o login."""
    logout(request)
    return redirect("login")


@login_required
def dashboard_view(request):
    """DASH-01: dashboard principal com KPIs reais de cotações."""
    quotations = Quotation.objects.select_related("customer").order_by("-created_at")
    totals = quotations.aggregate(
        total=Count("id"),
        pipeline=Sum("preco_com_impostos"),
        won=Count("id", filter=Q(status="won")),
        in_review=Count("id", filter=Q(status="in_review")),
    )
    active_count = totals["total"] or 0
    pipeline_total = totals["pipeline"] or Decimal("0")
    won_count = totals["won"] or 0
    in_review_count = totals["in_review"] or 0

    approved_hashes = set(
        TechnicalApproval.objects.filter(revoked_at__isnull=True).values_list("quotation_id", flat=True)
    )
    pending_approvals = quotations.filter(status="in_review").exclude(pk__in=approved_hashes)
    recent_rows = []
    for quotation in quotations[:5]:
        margin = quotation.preco_com_impostos - quotation.custo_total
        recent_rows.append(
            {
                "quotation": quotation,
                "margin": margin,
                "has_approval": quotation.pk in approved_hashes,
            }
        )

    return render(
        request,
        "accounts/dashboard.html",
        {
            "user": request.user,
            "active_count": active_count,
            "pipeline_total": pipeline_total,
            "won_count": won_count,
            "in_review_count": in_review_count,
            "pending_approvals": pending_approvals[:3],
            "recent_rows": recent_rows,
        },
    )
