"""
Middleware de isolamento de tenant a nível de usuário.

auth.User é global (schema public). O vínculo usuário↔tenant é o UserProfile, que
vive no schema de cada tenant. TenantMembershipMiddleware barra qualquer usuário
autenticado que NÃO tenha profile no schema ativo: encerra a sessão e manda para o
login. Fecha o vetor "usuário do tenant A loga no domínio do tenant B".

Roda depois de AuthenticationMiddleware (precisa de request.user) e de
TenantMainMiddleware (precisa do schema já resolvido).
"""
from django.contrib.auth import logout
from django.db import connection
from django.shortcuts import redirect
from django.urls import reverse
from django_tenants.utils import get_public_schema_name

from apps.accounts.rbac import has_tenant_membership


class TenantMembershipMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and connection.schema_name != get_public_schema_name()
            and not has_tenant_membership(user)
        ):
            logout(request)
            return redirect("login")
        return self.get_response(request)


class MustChangePasswordMiddleware:
    """
    Convite de membro seta UserProfile.must_change_password=True com senha
    provisória. Enquanto a flag estiver ligada, barra qualquer rota (exceto a
    própria troca de senha e o logout) e manda para a página de troca.
    """

    EXEMPT_URL_NAMES = ("change_password", "logout")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profile", None)
            if profile is not None and profile.must_change_password:
                exempt_paths = {reverse(name) for name in self.EXEMPT_URL_NAMES}
                if request.path not in exempt_paths:
                    return redirect("change_password")
        return self.get_response(request)
