"""
Views de sessão (session auth, sem JWT).
- login_view: autentica por username OU e-mail; HTMX-friendly (partial em erro).
- logout_view: encerra a sessão e volta ao login.
- dashboard_view: placeholder protegido por login.
"""
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import LoginForm


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
        if user is not None and user.is_active:
            login(request, user)
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
    """Placeholder de dashboard (exige login)."""
    return render(request, "accounts/dashboard.html", {"user": request.user})
