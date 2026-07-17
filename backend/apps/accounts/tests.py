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
from django.conf import settings
from django.test import RequestFactory

# TenantTestCase cria schema de tenant de teste; o URLconf de tenant (com /login/)
# só é roteado pelo TenantMainMiddleware quando o host = domínio do tenant.
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.accounts.rbac import ROLE_GROUPS, ensure_groups, require_role
from apps.audit.models import AccessLog


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


class TenantMemberInvitationTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.admin_user = User.objects.create_user(
            username="tenant-admin",
            email="admin@tenant.com",
            password="segredo123",
        )
        UserProfile.objects.create(
            user=self.admin_user,
            full_name="Alice Admin",
            role=UserProfile.ROLE_ADMIN,
            is_active=True,
        )

        self.non_admin_user = User.objects.create_user(
            username="tenant-orc",
            email="orc@tenant.com",
            password="segredo123",
        )
        UserProfile.objects.create(
            user=self.non_admin_user,
            full_name="Olivia Orc",
            role=UserProfile.ROLE_ORCAMENTISTA,
            is_active=True,
        )

    def test_admin_can_invite_orcamentista_with_temporary_password(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            "/members/invite/",
            {
                "email": "novo.orc@tenant.com",
                "full_name": "Novo Orc",
                "role": UserProfile.ROLE_ORCAMENTISTA,
                "phone": "11999999999",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        invited_user = User.objects.get(username="novo.orc@tenant.com")
        invited_profile = UserProfile.objects.get(user=invited_user)
        self.assertEqual(invited_user.email, "novo.orc@tenant.com")
        self.assertEqual(invited_profile.full_name, "Novo Orc")
        self.assertEqual(invited_profile.role, UserProfile.ROLE_ORCAMENTISTA)
        self.assertTrue(invited_profile.must_change_password)
        self.assertEqual(
            list(invited_user.groups.values_list("name", flat=True)),
            [ROLE_GROUPS[UserProfile.ROLE_ORCAMENTISTA]],
        )

        provisional_password = response.context["invitation_result"]["temporary_password"]
        self.assertTrue(invited_user.check_password(provisional_password))
        self.assertContains(response, "novo.orc@tenant.com")
        self.assertContains(response, provisional_password)
        self.assertContains(response, "/login/")

    def test_inviting_engenheiro_without_crea_shows_validation_error(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            "/members/invite/",
            {
                "email": "novo.eng@tenant.com",
                "full_name": "Novo Eng",
                "role": UserProfile.ROLE_ENGENHEIRO,
                "phone": "11999999999",
                "crea_number": "",
                "crea_state": "SP",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="novo.eng@tenant.com").exists())
        self.assertContains(response, "Engenheiro requer n", status_code=400)

    def test_non_admin_cannot_invite_member(self):
        self.client.force_login(self.non_admin_user)

        response = self.client.post(
            "/members/invite/",
            {
                "email": "bloqueado@tenant.com",
                "full_name": "Usuário Bloqueado",
                "role": UserProfile.ROLE_ORCAMENTISTA,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="bloqueado@tenant.com").exists())


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


class TenantMemberRoleChangeTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.admin_user = User.objects.create_user(username="tenant-admin", password="segredo123")
        self.admin_profile = UserProfile.objects.create(
            user=self.admin_user, full_name="Alice Admin", role=UserProfile.ROLE_ADMIN, is_active=True,
        )

        self.member_user = User.objects.create_user(username="membro-orc", password="segredo123")
        self.member_profile = UserProfile.objects.create(
            user=self.member_user, full_name="Bia Orc", role=UserProfile.ROLE_ORCAMENTISTA, is_active=True,
        )

        self.non_admin_user = User.objects.create_user(username="tenant-orc", password="segredo123")
        UserProfile.objects.create(
            user=self.non_admin_user, full_name="Olivia Orc", role=UserProfile.ROLE_ORCAMENTISTA, is_active=True,
        )

    def test_admin_muda_papel_de_membro_atualiza_group_e_gera_accesslog(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            f"/members/{self.member_profile.pk}/role/",
            {"role": UserProfile.ROLE_GESTOR_COMERCIAL},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.member_profile.refresh_from_db()
        self.assertEqual(self.member_profile.role, UserProfile.ROLE_GESTOR_COMERCIAL)
        self.assertEqual(
            list(self.member_user.groups.values_list("name", flat=True)),
            [ROLE_GROUPS[UserProfile.ROLE_GESTOR_COMERCIAL]],
        )
        log = AccessLog.objects.get(action="role_change")
        self.assertEqual(log.user_id, self.admin_user.pk)
        self.assertEqual(log.resource_id, str(self.member_profile.pk))
        self.assertEqual(log.metadata["old_role"], UserProfile.ROLE_ORCAMENTISTA)
        self.assertEqual(log.metadata["new_role"], UserProfile.ROLE_GESTOR_COMERCIAL)

    def test_mudar_papel_para_engenheiro_sem_crea_falha(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            f"/members/{self.member_profile.pk}/role/",
            {"role": UserProfile.ROLE_ENGENHEIRO},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.member_profile.refresh_from_db()
        self.assertEqual(self.member_profile.role, UserProfile.ROLE_ORCAMENTISTA)
        self.assertFalse(AccessLog.objects.filter(action="role_change").exists())

    def test_mudar_papel_para_engenheiro_com_crea_funciona(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            f"/members/{self.member_profile.pk}/role/",
            {"role": UserProfile.ROLE_ENGENHEIRO, "crea_number": "CREA-999", "crea_state": "SP"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.member_profile.refresh_from_db()
        self.assertEqual(self.member_profile.role, UserProfile.ROLE_ENGENHEIRO)
        self.assertEqual(self.member_profile.crea_number, "CREA-999")

    def test_nao_admin_nao_pode_mudar_papel(self):
        self.client.force_login(self.non_admin_user)

        response = self.client.post(
            f"/members/{self.member_profile.pk}/role/",
            {"role": UserProfile.ROLE_GESTOR_COMERCIAL},
        )

        self.assertEqual(response.status_code, 403)
        self.member_profile.refresh_from_db()
        self.assertEqual(self.member_profile.role, UserProfile.ROLE_ORCAMENTISTA)


class MustChangePasswordTests(TestCase):
    """
    Épico 5, task 4: primeiro login de membro convidado (must_change_password=True)
    força a troca de senha antes de acessar o resto do produto.
    """

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.invited_user = User.objects.create_user(username="convidado", password="senha-temp-123")
        self.invited_profile = UserProfile.objects.create(
            user=self.invited_user,
            full_name="Convidado Novo",
            role=UserProfile.ROLE_ORCAMENTISTA,
            is_active=True,
            must_change_password=True,
        )

        self.normal_user = User.objects.create_user(username="normal", password="senha-forte-123")
        UserProfile.objects.create(
            user=self.normal_user,
            full_name="Usuário Normal",
            role=UserProfile.ROLE_ORCAMENTISTA,
            is_active=True,
            must_change_password=False,
        )

    def test_membro_com_flag_e_redirecionado_para_troca_de_senha_ao_acessar_qualquer_pagina(self):
        self.client.force_login(self.invited_user)

        resp = self.client.get("/")

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/change-password/")

    def test_membro_com_flag_pode_acessar_a_propria_pagina_de_troca(self):
        self.client.force_login(self.invited_user)

        resp = self.client.get("/change-password/")

        self.assertEqual(resp.status_code, 200)

    def test_membro_com_flag_pode_fazer_logout(self):
        self.client.force_login(self.invited_user)

        resp = self.client.post("/logout/")

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/login/")

    def test_trocar_senha_com_sucesso_limpa_flag_e_libera_acesso(self):
        self.client.force_login(self.invited_user)

        resp = self.client.post(
            "/change-password/",
            {"new_password1": "senha-nova-super-forte", "new_password2": "senha-nova-super-forte"},
        )

        self.assertEqual(resp.status_code, 302)
        self.invited_profile.refresh_from_db()
        self.assertFalse(self.invited_profile.must_change_password)

        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

        self.client.logout()
        relogin = self.client.post(
            "/login/", {"identifier": "convidado", "password": "senha-nova-super-forte"}
        )
        self.assertEqual(relogin.status_code, 302)

    def test_trocar_senha_com_confirmacao_diferente_nao_limpa_flag(self):
        self.client.force_login(self.invited_user)

        resp = self.client.post(
            "/change-password/",
            {"new_password1": "senha-nova-super-forte", "new_password2": "outra-coisa-qualquer"},
        )

        self.assertEqual(resp.status_code, 200)
        self.invited_profile.refresh_from_db()
        self.assertTrue(self.invited_profile.must_change_password)

    def test_usuario_normal_nao_e_afetado(self):
        self.client.force_login(self.normal_user)

        resp = self.client.get("/")

        self.assertEqual(resp.status_code, 200)


class TenantMemberDeactivationTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.admin_user = User.objects.create_user(username="tenant-admin", password="segredo123")
        self.admin_profile = UserProfile.objects.create(
            user=self.admin_user, full_name="Alice Admin", role=UserProfile.ROLE_ADMIN, is_active=True,
        )

        self.member_user = User.objects.create_user(username="membro-orc", password="segredo123")
        self.member_profile = UserProfile.objects.create(
            user=self.member_user, full_name="Bia Orc", role=UserProfile.ROLE_ORCAMENTISTA, is_active=True,
        )

        self.non_admin_user = User.objects.create_user(username="tenant-orc", password="segredo123")
        UserProfile.objects.create(
            user=self.non_admin_user, full_name="Olivia Orc", role=UserProfile.ROLE_ORCAMENTISTA, is_active=True,
        )

    def test_admin_desativa_membro_seta_inactive_e_gera_accesslog(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            f"/members/{self.member_profile.pk}/deactivate/",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.member_profile.refresh_from_db()
        self.assertFalse(self.member_profile.is_active)
        log = AccessLog.objects.get(action="member_deactivate")
        self.assertEqual(log.user_id, self.admin_user.pk)
        self.assertEqual(log.resource_id, str(self.member_profile.pk))

    def test_admin_nao_pode_desativar_a_si_mesmo(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            f"/members/{self.admin_profile.pk}/deactivate/",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.admin_profile.refresh_from_db()
        self.assertTrue(self.admin_profile.is_active)
        self.assertFalse(AccessLog.objects.filter(action="member_deactivate").exists())

    def test_nao_admin_nao_pode_desativar_membro(self):
        self.client.force_login(self.non_admin_user)

        response = self.client.post(f"/members/{self.member_profile.pk}/deactivate/")

        self.assertEqual(response.status_code, 403)
        self.member_profile.refresh_from_db()
        self.assertTrue(self.member_profile.is_active)


class AxesBruteForceConfigTests(TestCase):
    """Contrato das settings do django-axes.

    Achado HIGH da auditoria /cso de 2026-07-17: a proteção de força bruta estava
    anulada. `AXES_LOCKOUT_PARAMETERS = ["ip_address"]` + django-ipware ausente faz o
    axes cair em REMOTE_ADDR (axes/helpers.py get_client_ip_address: CLIENT_IP_CALLABLE
    -> ipware -> REMOTE_ADDR). Como o deploy fica atrás de um túnel que termina TLS,
    REMOTE_ADDR é o endereço do cloudflared em toda request: a plataforma inteira
    dividia UM contador de lockout. Com `AXES_RESET_ON_SUCCESS = True`, qualquer login
    bem-sucedido zerava as falhas de todos — um atacante alternava 4 senhas erradas
    contra o admin e 1 login na própria conta, para sempre.

    Estes testes travam as duas pontas. São asserções sobre settings, não sobre
    comportamento, de propósito: o comportamento depende do IP de origem real, que não
    é reproduzível em teste unitário.
    """

    def test_lockout_parameters_include_username(self):
        """Sem username no bucket, o lockout é inútil atrás de um proxy: todos os
        usuários compartilham o IP do túnel e portanto o mesmo contador."""
        params = settings.AXES_LOCKOUT_PARAMETERS
        achatado = {
            item
            for entry in params
            for item in ([entry] if isinstance(entry, str) else entry)
        }
        self.assertIn(
            "username",
            achatado,
            "AXES_LOCKOUT_PARAMETERS precisa conter 'username'. Chavear só por "
            "ip_address anula a proteção atrás do Cloudflare Tunnel (REMOTE_ADDR é o "
            "mesmo para todos). Ver o comentário em settings/base.py.",
        )

    def test_reset_on_success_disabled(self):
        """Com RESET_ON_SUCCESS, o sucesso do atacante na própria conta apaga as
        falhas acumuladas contra a conta alvo que compartilha o bucket."""
        self.assertFalse(
            settings.AXES_RESET_ON_SUCCESS,
            "AXES_RESET_ON_SUCCESS deve ser False: um login bem-sucedido apagava os "
            "AccessAttempt do bucket inteiro, zerando o contador do alvo.",
        )

    def test_failure_limit_and_cooloff_still_set(self):
        """O lockout só existe se houver limite e janela."""
        self.assertGreater(settings.AXES_FAILURE_LIMIT, 0)
        self.assertTrue(settings.AXES_COOLOFF_TIME)

    def test_axes_backend_is_first(self):
        """AxesStandaloneBackend precisa ser o primeiro: se o ModelBackend autenticar
        antes, o axes nunca vê a tentativa."""
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS[0],
            "axes.backends.AxesStandaloneBackend",
        )
