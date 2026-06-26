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
