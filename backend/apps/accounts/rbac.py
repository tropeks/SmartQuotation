"""
RBAC (controle de acesso por papel) para o schema do tenant.
- ROLE_GROUPS mapeia cada role do UserProfile para um Group do Django.
- ensure_groups() cria os Groups (idempotente) — chamar no provisionamento do tenant.
- require_role(*roles) é um decorator de view que exige login + role permitido.
"""
from functools import wraps

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from apps.accounts.models import UserProfile

# Mapa role -> nome do Group (1:1 com os choices de UserProfile.ROLE).
ROLE_GROUPS = {
    UserProfile.ROLE_ORCAMENTISTA: "Orçamentista",
    UserProfile.ROLE_ENGENHEIRO: "Engenheiro",
    UserProfile.ROLE_GESTOR_COMERCIAL: "Gestor Comercial",
    UserProfile.ROLE_ADMIN: "Admin",
}


def ensure_groups():
    """Cria os Groups de cada role (idempotente). Retorna {role: Group}."""
    grupos = {}
    for role, nome in ROLE_GROUPS.items():
        grupos[role], _ = Group.objects.get_or_create(name=nome)
    return grupos


def user_role(user):
    """Retorna a role do usuário via profile, ou None se ausente."""
    profile = getattr(user, "profile", None)
    return profile.role if profile is not None else None


def has_tenant_membership(user):
    """
    Verdadeiro se `user` pertence ao tenant (schema) ATIVO da requisição.

    auth.User vive no schema public (SHARED_APPS) e é global; o vínculo do usuário
    com um tenant é o UserProfile (TENANT_APPS, por schema). Sem essa checagem, um
    usuário de um tenant conseguiria autenticar no domínio de outro e ler dados via
    views só-@login_required. Superuser/staff são operadores de plataforma (não são
    usuários-fim de tenant) e passam direto.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    return UserProfile.objects.filter(user=user, is_active=True).exists()


def require_role(*roles):
    """
    Decorator de view: exige usuário autenticado E com profile.role em `roles`.
    - Não autenticado -> redireciona para login.
    - Autenticado sem role permitido -> PermissionDenied (HTTP 403).
    """
    allowed = set(roles)

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return redirect("login")
            if user_role(user) not in allowed:
                raise PermissionDenied("Papel sem permissão para este recurso.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
