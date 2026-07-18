"""
Testes da página "Papéis" (RBAC V2 M2): CRUD de papéis como dado, colunas dinâmicas
na grade, guard-rails (teto, anti-lockout, compliance CREA×technical_sign) e reatribuição.

TenantTestCase: Role/RolePermission/UserProfile vivem no schema do tenant (seed nas migrações).
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.compliance import TECHNICAL_SIGN_CAP
from apps.access.enforcement import role_can
from apps.access.matrix import seed_access_matrix
from apps.access.models import RolePermission
from apps.accounts.models import Role, UserProfile


class RolesPageBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        seed_access_matrix()
        self.admin = User.objects.create_user(username="admin", password="x")
        UserProfile.objects.create(user=self.admin, full_name="Admin", role=UserProfile.ROLE_ADMIN)
        self.orca = User.objects.create_user(username="orca", password="x")
        UserProfile.objects.create(user=self.orca, full_name="Orca", role=UserProfile.ROLE_ORCAMENTISTA)

    def _create(self, **over):
        data = {"name": "Diretor Comercial", "description": "d", "cap": ["quotation.read"]}
        data.update(over)
        return self.client.post("/config/roles/create/", data)


class RolesListTests(RolesPageBase):
    def test_gate_role_manage(self):
        self.client.force_login(self.orca)
        self.assertEqual(self.client.get("/config/roles/").status_code, 403)

    def test_admin_ve_lista_com_built_ins(self):
        self.client.force_login(self.admin)
        resp = self.client.get("/config/roles/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "PAPÉIS")
        self.assertContains(resp, "Engenheiro")

    def test_new_from_template_prefills(self):
        self.client.force_login(self.admin)
        resp = self.client.get("/config/roles/new/?template=engenheiro")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Engenheiro")


class RoleCreateTests(RolesPageBase):
    def test_cria_papel_custom_e_persiste_matriz(self):
        self.client.force_login(self.admin)
        resp = self._create(name="Diretor Comercial", cap=["quotation.read", "proposal.write"])
        self.assertEqual(resp.status_code, 302)
        role = Role.objects.get(name="Diretor Comercial")
        self.assertFalse(role.is_seeded)
        self.assertEqual(role.key, "diretor-comercial")
        # linhas RolePermission criadas para TODAS as capabilities
        self.assertEqual(RolePermission.objects.filter(role=role.key).count(),
                         RolePermission.objects.filter(role=UserProfile.ROLE_ADMIN).count())
        self.assertTrue(role_can(role.key, "proposal.write"))
        self.assertFalse(role_can(role.key, "of.convert"))

    def test_cria_do_zero_sem_caps(self):
        self.client.force_login(self.admin)
        resp = self._create(name="Estagiário", cap=[])
        self.assertEqual(resp.status_code, 302)
        role = Role.objects.get(name="Estagiário")
        self.assertFalse(RolePermission.objects.filter(role=role.key, allowed=True).exists())

    def test_compliance_technical_sign_exige_requires_crea(self):
        self.client.force_login(self.admin)
        resp = self._create(name="Falso Eng", cap=[TECHNICAL_SIGN_CAP])  # sem requires_crea
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Role.objects.filter(name="Falso Eng").exists())

    def test_technical_sign_ok_com_requires_crea(self):
        self.client.force_login(self.admin)
        resp = self._create(name="Eng Custom", cap=[TECHNICAL_SIGN_CAP], requires_crea="on")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Role.objects.get(name="Eng Custom").requires_crea)

    def test_nome_vazio_400(self):
        self.client.force_login(self.admin)
        self.assertEqual(self._create(name="").status_code, 400)

    def test_teto_de_papeis(self):
        self.client.force_login(self.admin)
        # já há 5 built-ins; cria até 15, o 16º falha
        for i in range(10):
            self.assertEqual(self._create(name=f"Papel {i}").status_code, 302)
        self.assertEqual(Role.objects.count(), 15)
        self.assertEqual(self._create(name="Papel Extra").status_code, 400)


class RoleEditDeleteTests(RolesPageBase):
    def test_edita_traits_e_caps(self):
        self.client.force_login(self.admin)
        self._create(name="Comercial X", cap=["quotation.read"])
        role = Role.objects.get(name="Comercial X")
        resp = self.client.post("/config/roles/update/", {
            "key": role.key, "name": "Comercial X2", "description": "nova",
            "is_admin_like": "on", "cap": ["quotation.read", "material.read"],
        })
        self.assertEqual(resp.status_code, 302)
        role.refresh_from_db()
        self.assertEqual(role.name, "Comercial X2")
        self.assertTrue(role.is_admin_like)
        self.assertTrue(role_can(role.key, "material.read"))

    def test_anti_lockout_remove_role_manage_do_unico_detentor(self):
        # admin é o único com role.manage; salvar admin sem role.manage marcado -> 400
        self.client.force_login(self.admin)
        # monta o POST de update do admin com TODAS as caps atuais menos role.manage
        current = list(RolePermission.objects.filter(role=UserProfile.ROLE_ADMIN, allowed=True)
                       .values_list("capability", flat=True))
        caps = [c for c in current if c != "role.manage"]
        resp = self.client.post("/config/roles/update/", {
            "key": UserProfile.ROLE_ADMIN, "name": "Administrador", "cap": caps,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(role_can(UserProfile.ROLE_ADMIN, "role.manage"))

    def test_nao_exclui_built_in(self):
        self.client.force_login(self.admin)
        resp = self.client.post("/config/roles/delete/", {"key": UserProfile.ROLE_ENGENHEIRO})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("builtin", resp["Location"])
        self.assertTrue(Role.objects.filter(key=UserProfile.ROLE_ENGENHEIRO).exists())

    def test_exclui_custom_sem_usuarios(self):
        self.client.force_login(self.admin)
        self._create(name="Temp", cap=[])
        role = Role.objects.get(name="Temp")
        resp = self.client.post("/config/roles/delete/", {"key": role.key})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Role.objects.filter(key=role.key).exists())
        self.assertFalse(RolePermission.objects.filter(role=role.key).exists())

    def test_exclui_custom_com_usuarios_exige_reatribuicao(self):
        self.client.force_login(self.admin)
        self._create(name="Vendedor", cap=[])
        role = Role.objects.get(name="Vendedor")
        u = User.objects.create_user(username="vend", password="x")
        UserProfile.objects.create(user=u, full_name="Vend", role=role.key)
        # sem reassign_to -> não exclui
        resp = self.client.post("/config/roles/delete/", {"key": role.key})
        self.assertIn("need_reassign", resp["Location"])
        self.assertTrue(Role.objects.filter(key=role.key).exists())
        # com reassign_to -> move usuário e exclui
        resp = self.client.post("/config/roles/delete/", {
            "key": role.key, "reassign_to": UserProfile.ROLE_ORCAMENTISTA,
        })
        self.assertIn("deleted", resp["Location"])
        self.assertFalse(Role.objects.filter(key=role.key).exists())
        u.profile.refresh_from_db()
        self.assertEqual(u.profile.role, UserProfile.ROLE_ORCAMENTISTA)


class DynamicMatrixColumnsTests(RolesPageBase):
    def test_grade_mostra_coluna_de_papel_custom(self):
        self.client.force_login(self.admin)
        self._create(name="Consultor", cap=["quotation.read"])
        resp = self.client.get("/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Consultor")  # coluna dinâmica

    def test_toggle_em_papel_custom_funciona(self):
        self.client.force_login(self.admin)
        self._create(name="Consultor", cap=[])
        role = Role.objects.get(name="Consultor")
        self.assertFalse(role_can(role.key, "quotation.read"))
        resp = self.client.post("/config/toggle/", {
            "role": role.key, "capability": "quotation.read",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(role_can(role.key, "quotation.read"))

    def test_toggle_technical_sign_em_papel_sem_crea_bloqueado(self):
        self.client.force_login(self.admin)
        self._create(name="ComercialY", cap=[])
        role = Role.objects.get(name="ComercialY")
        resp = self.client.post("/config/toggle/", {
            "role": role.key, "capability": TECHNICAL_SIGN_CAP,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(role_can(role.key, TECHNICAL_SIGN_CAP))
