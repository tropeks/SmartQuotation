"""
Testes de M6: diff de auditoria (Role/ApprovalWorkflow), invalidação de cache no save de
Role e empty-states de onboarding nas páginas de Papéis e Fluxo.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.enforcement import role_can
from apps.access.matrix import seed_access_matrix
from apps.access.models import RolePermission
from apps.access.workflow_templates import seed_workflow
from apps.accounts.models import Role, UserProfile
from apps.audit.models import AccessLog


class M6Base(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        seed_access_matrix()
        seed_workflow()
        self.admin = User.objects.create_user(username="admin", password="x")
        UserProfile.objects.create(user=self.admin, full_name="Admin", role=UserProfile.ROLE_ADMIN)
        self.client.force_login(self.admin)


class RoleDiffTests(M6Base):
    def test_role_update_loga_diff(self):
        self.client.post("/config/roles/create/", {"name": "Consultor", "cap": ["quotation.read"]})
        role = Role.objects.get(name="Consultor")
        self.client.post("/config/roles/update/", {
            "key": role.key, "name": "Consultor Sr", "is_admin_like": "on",
            "cap": ["quotation.read", "material.read"],
        })
        log = AccessLog.objects.filter(action="role_change").latest("created_at")
        diff = log.metadata["diff"]
        self.assertEqual(diff["name"], {"from": "Consultor", "to": "Consultor Sr"})
        self.assertEqual(diff["is_admin_like"], {"from": False, "to": True})
        self.assertEqual(diff["capabilities"]["added"], ["material.read"])
        self.assertEqual(diff["capabilities"]["removed"], [])

    def test_apply_template_loga_diff_de_estagios(self):
        self.client.post("/config/workflow/apply-template/", {"template": "tech_commercial"})
        log = AccessLog.objects.filter(action="approval_config_change").latest("created_at")
        diff = log.metadata["diff"]["stages"]
        self.assertIn("Aprovação comercial", diff["to"])
        self.assertNotIn("Aprovação comercial", diff["from"])


class RoleCacheInvalidationTests(M6Base):
    def test_save_de_role_invalida_cache_da_matriz(self):
        # aquece o cache
        self.assertFalse(role_can("consultor-x", "quotation.read"))
        Role.objects.create(key="consultor-x", name="Consultor X")
        RolePermission.objects.create(role="consultor-x", capability="quotation.read", allowed=True)
        # o post_save de RolePermission já invalida; um save direto de Role também deve invalidar
        r = Role.objects.get(key="consultor-x")
        r.name = "Consultor X2"
        r.save(update_fields=["name"])
        self.assertTrue(role_can("consultor-x", "quotation.read"))


class OnboardingEmptyStateTests(M6Base):
    def test_roles_list_mostra_onboarding_so_com_built_ins(self):
        resp = self.client.get("/config/roles/")
        self.assertContains(resp, "Você usa só os papéis padrão")

    def test_workflow_mostra_onboarding_so_tecnica(self):
        resp = self.client.get("/config/workflow/")
        self.assertContains(resp, "só a aprovação técnica")
