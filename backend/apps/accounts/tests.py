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
        # bob pertence a ESTE tenant -> precisa de UserProfile no schema ativo.
        UserProfile.objects.create(
            user=self.user, full_name="Bob", role=UserProfile.ROLE_ORCAMENTISTA
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


class TenantMembershipTests(TestCase):
    """
    Isolamento user↔tenant: auth.User é global (schema public), mas só quem tem
    UserProfile no schema ativo é membro do tenant. Um user sem profile no schema
    (= usuário de OUTRO tenant) não pode logar nem navegar.
    """

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        # Usuário SEM UserProfile neste schema -> simula usuário de outro tenant.
        self.outsider = User.objects.create_user(
            username="intruso", password="senha-forte-123"
        )

    def test_login_negado_sem_profile_no_tenant(self):
        resp = self.client.post(
            "/login/", {"identifier": "intruso", "password": "senha-forte-123"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_middleware_desloga_acesso_sem_profile(self):
        # force_login burla o gate do login_view; o middleware deve barrar na navegação.
        self.client.force_login(self.outsider)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_superuser_sem_profile_passa(self):
        su = User.objects.create_superuser(
            username="root", email="root@x.com", password="senha-forte-123"
        )
        resp = self.client.post(
            "/login/", {"identifier": "root", "password": "senha-forte-123"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_membro_com_profile_navega(self):
        membro = User.objects.create_user(
            username="membro", password="senha-forte-123"
        )
        UserProfile.objects.create(
            user=membro, full_name="Membro", role=UserProfile.ROLE_ORCAMENTISTA
        )
        self.client.force_login(membro)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)


class ShellSmokeTests(TestCase):
    """Smoke test: verifica que o shell (base.html) renderiza com Alpine.js, CSS, e navegação profissional."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(
            username="alice", email="alice@empresa.com", password="senha-forte-123"
        )
        UserProfile.objects.create(
            user=self.user, full_name="Alice", role=UserProfile.ROLE_ORCAMENTISTA
        )

    def test_shell_carrega_alpine_js(self):
        """Base.html deve incluir Alpine.js (CDN)."""
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alpine", count=None)  # Alpine.js via CDN

    def test_shell_carrega_design_system_css(self):
        """Base.html deve referenciar design-system-g.css."""
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "design-system-g.css")

    def test_shell_tem_rail_marca(self):
        """Rail horizontal deve existir com marca SMARTQUOTATION."""
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SMARTQUOTATION")
        self.assertContains(resp, "g-rail")

    def test_shell_tem_navegacao_modulos(self):
        """Shell deve exibir navegação de módulos: Cotações, OFs, Custos, TEMA, Permutador."""
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cotações")
        self.assertContains(resp, "OFs")
        self.assertContains(resp, "Custos")
        self.assertContains(resp, "TEMA")

    def test_dashboard_command_center_mostra_kpis_reais(self):
        from decimal import Decimal
        from apps.quotations.models import Customer, Quotation

        customer = Customer.objects.create(company_name="Cliente Dashboard")
        Quotation.objects.create(
            number="COT-2026-001",
            customer=customer,
            title="Feixe ganho",
            status=Quotation.STATUS[4][0],
            preco_com_impostos=Decimal("125000.00"),
            custo_total=Decimal("100000.00"),
        )
        Quotation.objects.create(
            number="COT-2026-002",
            customer=customer,
            title="Feixe em revisão",
            status="in_review",
            preco_com_impostos=Decimal("98000.00"),
            custo_total=Decimal("76000.00"),
        )

        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "DASH-01")
        self.assertContains(resp, "Command Center")
        self.assertContains(resp, "g3-minimap")
        self.assertContains(resp, "Cotações Ativas")
        self.assertContains(resp, "2")
        self.assertContains(resp, "Pipeline")
        self.assertContains(resp, "R$ 223.000,00")  # pt-BR: separador de milhar (filtro brl)
        self.assertContains(resp, "Ganhas")
        self.assertContains(resp, "1")
        self.assertContains(resp, "Em Revisão")
        self.assertContains(resp, "Feixe em revisão")
        self.assertContains(resp, "Cliente Dashboard")


class TenantMembersViewTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.admin_user = User.objects.create_user(username="tenant-admin", password="segredo123")
        UserProfile.objects.create(
            user=self.admin_user,
            full_name="Alice Admin",
            role=UserProfile.ROLE_ADMIN,
            is_active=True,
        )

        self.engineer_user = User.objects.create_user(username="eng-tenant", password="segredo123")
        UserProfile.objects.create(
            user=self.engineer_user,
            full_name="Bruno Eng",
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-12345",
            crea_state="SP",
            is_active=True,
        )

        self.viewer_user = User.objects.create_user(username="orc-tenant", password="segredo123")
        UserProfile.objects.create(
            user=self.viewer_user,
            full_name="Caio Orc",
            role=UserProfile.ROLE_ORCAMENTISTA,
            is_active=False,
        )

    def test_get_members_as_admin_returns_200_with_tenant_members(self):
        self.client.force_login(self.admin_user)

        response = self.client.get("/members/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MEMBROS DO TENANT")
        self.assertContains(response, "Alice Admin")
        self.assertContains(response, "Bruno Eng")
        self.assertContains(response, "Caio Orc")
        self.assertContains(response, "Admin")
        self.assertContains(response, "Engenheiro")
        self.assertContains(response, "Orçamentista")
        self.assertContains(response, "Ativo")
        self.assertContains(response, "Inativo")
        self.assertContains(response, "CREA-12345")

    def test_get_members_as_non_admin_returns_403(self):
        self.client.force_login(self.engineer_user)

        response = self.client.get("/members/")

        self.assertEqual(response.status_code, 403)


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
