"""
EPICO 5, task 5/5 — Teste de aceite end-to-end.

Critério da SPEC (docs/SPEC_BETA_100.md, Épico 5): "admin do tenant convida
orçamentista → novo usuário loga e cria cotação; viewer não edita."

Fluxo validado:
1. Admin convida um orçamentista (senha provisória).
2. Novo usuário loga com a senha provisória.
3. É forçado a trocar a senha (must_change_password) antes de qualquer outra rota.
4. Após trocar a senha, consegue criar uma cotação (rota de escrita).

NOTA: hoje não existe um papel puramente "viewer" (somente-leitura) entre os 4
papéis (orcamentista/engenheiro/gestor_comercial/admin) — todos os 4 têm
permissão de escrita em cotações (_WRITE_ROLES do apps.quotations.views inclui
os 4). Por isso o assert de bloqueio usa o papel de MENOR privilégio de
escrita disponível (orçamentista) contra uma rota de escrita ADMIN-ONLY
(convite de membro), que é a fronteira de RBAC real hoje. Um papel
viewer/somente-leitura dedicado pode ser um refinamento posterior da spec.
"""
from django.contrib.auth.models import User
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.quotations.models import Customer, Quotation


class Epic5E2EAcceptanceTests(TenantTestCase):
    def setUp(self):
        call_command("seed_engineering_params", verbosity=0)
        call_command("seed_materials", verbosity=0)

        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.admin_user = User.objects.create_user(
            username="admin@engematex.com",
            email="admin@engematex.com",
            password="senha-forte-123",
        )
        UserProfile.objects.create(
            user=self.admin_user,
            full_name="Admin Tenant",
            role=UserProfile.ROLE_ADMIN,
            is_active=True,
        )

        self.customer = Customer.objects.create(company_name="Cliente Epic5")

    def test_admin_convida_orcamentista_novo_usuario_troca_senha_e_cria_cotacao(self):
        # 1) Admin convida um orçamentista -> senha provisória.
        self.client.force_login(self.admin_user)
        invite_resp = self.client.post(
            "/members/invite/",
            {
                "email": "novo.orc@engematex.com",
                "full_name": "Novo Orçamentista",
                "role": UserProfile.ROLE_ORCAMENTISTA,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(invite_resp.status_code, 200)
        invited_profile = UserProfile.objects.get(user__username="novo.orc@engematex.com")
        self.assertTrue(invited_profile.must_change_password)
        temporary_password = invite_resp.context["invitation_result"]["temporary_password"]
        self.client.logout()

        # 2) Novo usuário loga com a senha provisória.
        login_resp = self.client.post(
            "/login/",
            {"identifier": "novo.orc@engematex.com", "password": temporary_password},
        )
        self.assertEqual(login_resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

        # 3) É forçado a trocar a senha antes de acessar qualquer outra rota.
        blocked_resp = self.client.get("/cotacoes/nova/")
        self.assertEqual(blocked_resp.status_code, 302)
        self.assertEqual(blocked_resp.url, "/change-password/")

        change_resp = self.client.post(
            "/change-password/",
            {
                "new_password1": "senha-nova-super-forte",
                "new_password2": "senha-nova-super-forte",
            },
        )
        self.assertEqual(change_resp.status_code, 302)
        invited_profile.refresh_from_db()
        self.assertFalse(invited_profile.must_change_password)

        # 4) Consegue criar uma cotação (rota de escrita liberada ao orçamentista).
        create_resp = self.client.post(
            "/cotacoes/nova/",
            {"customer": self.customer.pk, "title": "Feixe Epic5 aceite"},
        )
        self.assertEqual(create_resp.status_code, 302)
        created = Quotation.objects.filter(
            title="Feixe Epic5 aceite", created_by__username="novo.orc@engematex.com"
        )
        self.assertTrue(created.exists())
        self.assertIsNotNone(created.get().custo_total)

    def test_papel_de_menor_privilegio_de_escrita_e_barrado_em_rota_administrativa(self):
        """Sem papel 'viewer' dedicado, valida a fronteira de RBAC real: o
        orçamentista (menor privilégio de escrita entre os 4 papéis) recebe 403
        ao tentar uma rota de escrita administrativa (convidar outro membro)."""
        orcamentista_user = User.objects.create_user(
            username="orc@engematex.com", password="senha-forte-123"
        )
        UserProfile.objects.create(
            user=orcamentista_user,
            full_name="Orçamentista Comum",
            role=UserProfile.ROLE_ORCAMENTISTA,
            is_active=True,
        )
        self.client.force_login(orcamentista_user)

        resp = self.client.post(
            "/members/invite/",
            {
                "email": "bloqueado@engematex.com",
                "full_name": "Bloqueado",
                "role": UserProfile.ROLE_ORCAMENTISTA,
            },
        )

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(User.objects.filter(username="bloqueado@engematex.com").exists())
