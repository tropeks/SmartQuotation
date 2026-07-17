"""
Testes da UI de configuração (T6): grade papel×capability + toggle HTMX.

Cobre: admin edita célula -> persiste -> role_can reflete; não-admin -> 403;
role/capability inválido -> 400; anti-lockout (não remove o último access.manage);
auditoria (AccessLog "permission_change") registrada.

TenantTestCase: RolePermission/AccessLog são models de TENANT (vivem no schema).
"""
from django.contrib.auth.models import User
from django.core.cache import cache

from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.enforcement import role_can
from apps.access.matrix import seed_access_matrix
from apps.access.models import RolePermission
from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog


class AccessConfigViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        seed_access_matrix()

        self.admin = User.objects.create_user(username="admin", password="x")
        UserProfile.objects.create(
            user=self.admin, full_name="Admin", role=UserProfile.ROLE_ADMIN
        )
        self.orca = User.objects.create_user(username="orca", password="x")
        UserProfile.objects.create(
            user=self.orca, full_name="Orca", role=UserProfile.ROLE_ORCAMENTISTA
        )

    # ── grade (GET) ──────────────────────────────────────────────────────
    def test_admin_ve_a_grade(self):
        self.client.force_login(self.admin)
        resp = self.client.get("/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "NÍVEIS DE ACESSO")
        self.assertContains(resp, "cap-row-quotation-create")

    def test_nao_admin_recebe_403_na_grade(self):
        self.client.force_login(self.orca)
        resp = self.client.get("/config/")
        self.assertEqual(resp.status_code, 403)

    # ── toggle (POST) ────────────────────────────────────────────────────
    def test_admin_edita_celula_persiste_e_reflete_em_role_can(self):
        # viewer NÃO cria cotação no default -> ligar deve refletir.
        self.assertFalse(role_can(UserProfile.ROLE_VIEWER, "quotation.create"))
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_VIEWER, "capability": "quotation.create"},
        )
        self.assertEqual(resp.status_code, 200)
        rp = RolePermission.objects.get(
            role=UserProfile.ROLE_VIEWER, capability="quotation.create"
        )
        self.assertTrue(rp.allowed)
        self.assertEqual(rp.updated_by_id, self.admin.pk)
        cache.clear()
        self.assertTrue(role_can(UserProfile.ROLE_VIEWER, "quotation.create"))

    def test_toggle_desliga_capability_ligada(self):
        self.assertTrue(role_can(UserProfile.ROLE_ENGENHEIRO, "of.convert"))
        self.client.force_login(self.admin)
        self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_ENGENHEIRO, "capability": "of.convert"},
        )
        rp = RolePermission.objects.get(
            role=UserProfile.ROLE_ENGENHEIRO, capability="of.convert"
        )
        self.assertFalse(rp.allowed)

    def test_nao_admin_recebe_403_no_toggle(self):
        self.client.force_login(self.orca)
        resp = self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_VIEWER, "capability": "quotation.create"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_role_invalido_400(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/config/toggle/",
            {"role": "papel_inexistente", "capability": "quotation.create"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_capability_invalida_400(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_ADMIN, "capability": "cap.inexistente"},
        )
        self.assertEqual(resp.status_code, 400)

    # ── anti-lockout ─────────────────────────────────────────────────────
    def test_anti_lockout_recusa_desligar_ultimo_access_manage(self):
        # Só admin tem access.manage por default -> desligar travaria o tenant.
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_ADMIN, "capability": "access.manage"},
        )
        self.assertEqual(resp.status_code, 400)
        rp = RolePermission.objects.get(
            role=UserProfile.ROLE_ADMIN, capability="access.manage"
        )
        self.assertTrue(rp.allowed)  # permaneceu ligado

    def test_anti_lockout_permite_desligar_se_outro_papel_mantem(self):
        # Concede access.manage ao gestor -> admin pode então perder o seu.
        RolePermission.objects.filter(
            role=UserProfile.ROLE_GESTOR_COMERCIAL, capability="access.manage"
        ).update(allowed=True)
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_ADMIN, "capability": "access.manage"},
        )
        self.assertEqual(resp.status_code, 200)
        rp = RolePermission.objects.get(
            role=UserProfile.ROLE_ADMIN, capability="access.manage"
        )
        self.assertFalse(rp.allowed)

    # ── auditoria ────────────────────────────────────────────────────────
    def test_toggle_registra_auditoria(self):
        self.client.force_login(self.admin)
        self.client.post(
            "/config/toggle/",
            {"role": UserProfile.ROLE_VIEWER, "capability": "quotation.create"},
        )
        log = AccessLog.objects.filter(action="permission_change").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user_id, self.admin.pk)
        self.assertEqual(log.resource_type, "RolePermission")
        self.assertEqual(log.metadata["capability"], "quotation.create")
        self.assertTrue(log.metadata["allowed"])
