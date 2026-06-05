"""
Testes do app accounts (Django TestCase — self-contained).
Cobre: regra engenheiro->CREA (clean + constraint), login/logout de sessão e
gating por papel via require_role.

ROOT_URLCONF é sobrescrito para apps.accounts.urls porque a integração das rotas
no URLconf do projeto é feita pelo agente pai (após settings + migrations).
"""
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.test import RequestFactory

# TenantTestCase cria schema de tenant de teste; o URLconf de tenant (com /login/)
# só é roteado pelo TenantMainMiddleware quando o host = domínio do tenant.
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.accounts.rbac import ROLE_GROUPS, ensure_groups, require_role


class UserProfileModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="senha-forte-123")

    def test_engenheiro_sem_crea_falha_no_clean(self):
        profile = UserProfile(
            user=self.user, full_name="Ana Eng", role=UserProfile.ROLE_ENGENHEIRO
        )
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_engenheiro_sem_crea_falha_na_constraint(self):
        # Bypassa o clean() e grava direto -> a CheckConstraint do banco deve barrar.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserProfile.objects.create(
                    user=self.user,
                    full_name="Ana Eng",
                    role=UserProfile.ROLE_ENGENHEIRO,
                    crea_number="",
                )

    def test_engenheiro_com_crea_ok(self):
        profile = UserProfile.objects.create(
            user=self.user,
            full_name="Ana Eng",
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="SP-123456",
            crea_state="SP",
        )
        self.assertEqual(profile.role, UserProfile.ROLE_ENGENHEIRO)

    def test_orcamentista_sem_crea_ok(self):
        profile = UserProfile.objects.create(
            user=self.user, full_name="Ana Orc", role=UserProfile.ROLE_ORCAMENTISTA
        )
        profile.full_clean()  # não deve levantar
        self.assertEqual(str(profile), "Ana Orc (orcamentista)")


class AuthViewTests(TestCase):
    def setUp(self):
        # roteia o client para o domínio do tenant de teste -> URLconf de tenant
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(
            username="bob", email="bob@empresa.com", password="senha-forte-123"
        )

    def test_login_autentica_e_cria_sessao(self):
        resp = self.client.post(
            "/login/", {"identifier": "bob", "password": "senha-forte-123"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_por_email(self):
        resp = self.client.post(
            "/login/", {"identifier": "bob@empresa.com", "password": "senha-forte-123"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_credenciais_invalidas(self):
        resp = self.client.post(
            "/login/", {"identifier": "bob", "password": "errada"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_limpa_sessao(self):
        self.client.force_login(self.user)
        self.assertIn("_auth_user_id", self.client.session)
        resp = self.client.post("/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)


class RbacTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="carla", password="senha-forte-123")
        self.profile = UserProfile.objects.create(
            user=self.user, full_name="Carla", role=UserProfile.ROLE_GESTOR_COMERCIAL
        )

    def test_ensure_groups_idempotente(self):
        from django.contrib.auth.models import Group

        ensure_groups()
        ensure_groups()  # 2a chamada não deve duplicar
        self.assertEqual(Group.objects.count(), len(ROLE_GROUPS))

    def _view(self, *roles):
        @require_role(*roles)
        def view(request):
            return HttpResponse("ok")

        return view

    def test_require_role_permite_role_correto(self):
        request = self.factory.get("/")
        request.user = self.user
        resp = self._view(UserProfile.ROLE_GESTOR_COMERCIAL)(request)
        self.assertEqual(resp.status_code, 200)

    def test_require_role_nega_role_errado(self):
        request = self.factory.get("/")
        request.user = self.user
        with self.assertRaises(PermissionDenied):
            self._view(UserProfile.ROLE_ADMIN)(request)

    def test_require_role_redireciona_anonimo(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()
        resp = self._view(UserProfile.ROLE_ADMIN)(request)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/login/")
