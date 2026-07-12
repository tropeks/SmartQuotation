"""
EPICO 5, task 5/5 — Teste de aceite end-to-end.

Critério da SPEC (docs/SPEC_BETA_100.md, Épico 5): "admin do tenant convida
orçamentista → novo usuário loga e cria cotação; viewer não edita."

Fluxos validados:
1. Admin convida um orçamentista (senha provisória).
2. Novo usuário loga com a senha provisória.
3. É forçado a trocar a senha (must_change_password) antes de qualquer outra rota.
4. Após trocar a senha, consegue criar uma cotação (rota de escrita).
5. Admin convida um viewer, que pode ler a cotação existente mas não editá-la.
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

    def test_admin_convida_viewer_que_loga_troca_senha_le_cotacao_e_nao_edita(self):
        quotation = Quotation.objects.create(
            customer=self.customer,
            title="Cotacao existente",
            created_by=self.admin_user,
        )

        self.client.force_login(self.admin_user)
        invite_resp = self.client.post(
            "/members/invite/",
            {
                "email": "viewer@engematex.com",
                "full_name": "Viewer Tenant",
                "role": UserProfile.ROLE_VIEWER,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(invite_resp.status_code, 200)
        invited_profile = UserProfile.objects.get(user__username="viewer@engematex.com")
        self.assertTrue(invited_profile.must_change_password)
        temporary_password = invite_resp.context["invitation_result"]["temporary_password"]
        self.client.logout()

        login_resp = self.client.post(
            "/login/",
            {"identifier": "viewer@engematex.com", "password": temporary_password},
        )
        self.assertEqual(login_resp.status_code, 302)

        blocked_before_change = self.client.get(f"/cotacoes/{quotation.pk}/editar/")
        self.assertEqual(blocked_before_change.status_code, 302)
        self.assertEqual(blocked_before_change.url, "/change-password/")

        change_resp = self.client.post(
            "/change-password/",
            {
                "new_password1": "senha-nova-viewer-forte",
                "new_password2": "senha-nova-viewer-forte",
            },
        )
        self.assertEqual(change_resp.status_code, 302)
        invited_profile.refresh_from_db()
        self.assertFalse(invited_profile.must_change_password)

        detail_resp = self.client.get(f"/cotacoes/{quotation.pk}/")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Cotacao existente")

        edit_resp = self.client.get(f"/cotacoes/{quotation.pk}/editar/")
        self.assertEqual(edit_resp.status_code, 403)
