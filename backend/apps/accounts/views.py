"""
Views de sessão (session auth, sem JWT).
- login_view: autentica por username OU e-mail; HTMX-friendly (partial em erro).
- logout_view: encerra a sessão e volta ao login.
- dashboard_view: dashboard executivo protegido por login.
"""
from decimal import Decimal
import secrets

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import LoginForm, MemberInviteForm
from apps.accounts.models import UserProfile
from apps.accounts.rbac import ensure_groups, require_role
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


@require_role(UserProfile.ROLE_ADMIN)
def members_view(request):
    query = (request.GET.get("q") or "").strip()
    members = UserProfile.objects.select_related("user").order_by("full_name")
    if query:
        members = members.filter(
            Q(full_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(crea_number__icontains=query)
        )

    context = {
        "members": members,
        "search": query,
        "active_members": members.filter(is_active=True).count(),
        "inactive_members": members.filter(is_active=False).count(),
        "engineers": members.filter(role=UserProfile.ROLE_ENGENHEIRO).count(),
        "invite_form": MemberInviteForm(),
        "invitation_result": None,
    }
    template = "accounts/_members_table.html" if _is_htmx(request) else "accounts/members.html"
    return render(request, template, context)


@require_POST
@require_role(UserProfile.ROLE_ADMIN)
def invite_member_view(request):
    form = MemberInviteForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "accounts/_member_invite_form.html",
            {"invite_form": form, "invitation_result": None},
            status=400,
        )

    ensure_groups()
    temporary_password = secrets.token_urlsafe(12)

    with transaction.atomic():
        user = User.objects.create_user(
            username=form.cleaned_data["email"],
            email=form.cleaned_data["email"],
            password=temporary_password,
        )
        profile = UserProfile(
            user=user,
            full_name=form.cleaned_data["full_name"],
            role=form.cleaned_data["role"],
            crea_number=form.cleaned_data.get("crea_number", ""),
            crea_state=(form.cleaned_data.get("crea_state", "") or "").upper(),
            phone=form.cleaned_data.get("phone", ""),
            is_active=True,
            must_change_password=True,
        )
        try:
            profile.full_clean()
        except ValidationError as exc:
            transaction.set_rollback(True)
            user.delete()
            for field, messages in exc.message_dict.items():
                for message in messages:
                    form.add_error(field, message)
            return render(
                request,
                "accounts/_member_invite_form.html",
                {"invite_form": form, "invitation_result": None},
                status=400,
            )
        profile.save()
        role_group = ensure_groups()[profile.role]
        user.groups.set([role_group])

    context = {
        "invite_form": MemberInviteForm(),
        "invitation_result": {
            "email": user.email,
            "temporary_password": temporary_password,
            "login_url": reverse("login"),
            "full_name": profile.full_name,
            "role_label": profile.get_role_display(),
        },
    }
    return render(request, "accounts/_member_invite_form.html", context)
