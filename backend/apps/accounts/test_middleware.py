"""Unit tests for MustChangePasswordMiddleware schema-awareness.

No schema `public` a tabela `accounts_userprofile` (TENANT_APPS) não existe, então
tocar `user.profile` para um staff autenticado no `/admin/` público quebra com erro
de banco. O middleware precisa pular o schema public, igual ao TenantMembershipMiddleware.

SimpleTestCase (sem DB): mockamos `connection.schema_name` e usamos um user cujo
acesso a `.profile` estoura — provando que o middleware NÃO deve consultá-lo no public.
"""
from types import SimpleNamespace
from unittest import mock

from django.db import ProgrammingError
from django.test import SimpleTestCase
from django_tenants.utils import get_public_schema_name

from apps.accounts.middleware import MustChangePasswordMiddleware


class _ExplodingProfileUser:
    is_authenticated = True

    @property
    def profile(self):  # simula a tabela ausente no schema public
        raise ProgrammingError('relation "accounts_userprofile" does not exist')


class MustChangePasswordMiddlewarePublicSchemaTests(SimpleTestCase):
    def _mw(self):
        sentinel = object()
        return MustChangePasswordMiddleware(lambda req: sentinel), sentinel

    def test_skips_profile_lookup_on_public_schema(self):
        """No schema public o middleware passa direto, SEM tocar user.profile."""
        mw, sentinel = self._mw()
        request = SimpleNamespace(user=_ExplodingProfileUser(), path="/admin/")
        with mock.patch("apps.accounts.middleware.connection") as conn:
            conn.schema_name = get_public_schema_name()
            result = mw(request)  # não pode levantar ProgrammingError
        self.assertIs(result, sentinel)

    def test_still_consults_profile_on_tenant_schema(self):
        """O guard só pula o public — em schema de tenant o profile É consultado."""
        mw, _ = self._mw()
        request = SimpleNamespace(user=_ExplodingProfileUser(), path="/qualquer/")
        with mock.patch("apps.accounts.middleware.connection") as conn:
            conn.schema_name = "tenant_abc"
            with self.assertRaises(ProgrammingError):
                mw(request)
