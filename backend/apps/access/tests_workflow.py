"""
Testes do builder de fluxo de aprovação (RBAC V2 M3): ApprovalWorkflow + estágios
ordenados, aplicação de templates, add/edit/remove/move de estágios, wiring papel→
capability (Nota A) e slots custom. Gate access.manage.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.enforcement import role_can
from apps.access.matrix import seed_access_matrix
from apps.access.models import ApprovalStage, ApprovalWorkflow, RolePermission
from apps.access.workflow_templates import CUSTOM_SIGN_SLOTS, seed_workflow
from apps.accounts.models import Role, UserProfile


class WorkflowBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        seed_access_matrix()
        seed_workflow()
        self.admin = User.objects.create_user(username="admin", password="x")
        UserProfile.objects.create(user=self.admin, full_name="Admin", role=UserProfile.ROLE_ADMIN)
        self.orca = User.objects.create_user(username="orca", password="x")
        UserProfile.objects.create(user=self.orca, full_name="Orca", role=UserProfile.ROLE_ORCAMENTISTA)

    def wf(self):
        return ApprovalWorkflow.objects.get(action_type="of.convert")


class WorkflowSeedTests(WorkflowBase):
    def test_workflow_default_e_estagio_tecnico_anexado(self):
        wf = self.wf()
        self.assertEqual(wf.action_type, "of.convert")
        tech = ApprovalStage.objects.get(key="technical")
        self.assertEqual(tech.workflow_id, wf.pk)
        self.assertTrue(tech.is_builtin)

    def test_gate_access_manage(self):
        self.client.force_login(self.orca)
        self.assertEqual(self.client.get("/config/workflow/").status_code, 403)

    def test_admin_ve_builder(self):
        self.client.force_login(self.admin)
        resp = self.client.get("/config/workflow/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "FLUXO DE APROVAÇÕES")
        self.assertContains(resp, "Aprovação técnica")


class ApplyTemplateTests(WorkflowBase):
    def test_aplica_tech_commercial(self):
        self.client.force_login(self.admin)
        resp = self.client.post("/config/workflow/apply-template/", {"template": "tech_commercial"})
        self.assertEqual(resp.status_code, 302)
        wf = self.wf()
        keys = set(wf.stages.values_list("key", flat=True))
        self.assertIn("technical", keys)
        self.assertIn("commercial", keys)
        commercial = wf.stages.get(key="commercial")
        self.assertEqual(commercial.approver_capability, "approval.commercial_sign")
        self.assertTrue(commercial.required)
        self.assertFalse(commercial.is_builtin)

    def test_reaplicar_substitui_nao_builtin_preserva_tecnico(self):
        self.client.force_login(self.admin)
        self.client.post("/config/workflow/apply-template/", {"template": "tech_comm_quality"})
        self.assertEqual(self.wf().stages.filter(is_builtin=False).count(), 2)
        self.client.post("/config/workflow/apply-template/", {"template": "technical_only"})
        wf = self.wf()
        self.assertEqual(wf.stages.filter(is_builtin=False).count(), 0)
        self.assertTrue(wf.stages.filter(key="technical", is_builtin=True).exists())

    def test_template_invalido_400_notice(self):
        self.client.force_login(self.admin)
        resp = self.client.post("/config/workflow/apply-template/", {"template": "xxx"})
        self.assertIn("bad_template", resp["Location"])


class StageCrudTests(WorkflowBase):
    def test_add_stage_consome_slot_e_concede_capability(self):
        self.client.force_login(self.admin)
        resp = self.client.post("/config/workflow/stage/add/", {
            "label": "Aprovação da diretoria", "approver_role": UserProfile.ROLE_GESTOR_COMERCIAL,
        })
        self.assertEqual(resp.status_code, 302)
        stage = self.wf().stages.get(label="Aprovação da diretoria")
        self.assertEqual(stage.approver_capability, CUSTOM_SIGN_SLOTS[0])
        self.assertTrue(role_can(UserProfile.ROLE_GESTOR_COMERCIAL, CUSTOM_SIGN_SLOTS[0]))

    def test_add_stage_sem_label_400(self):
        self.client.force_login(self.admin)
        resp = self.client.post("/config/workflow/stage/add/", {"label": ""})
        self.assertIn("need_label", resp["Location"])

    def test_esgota_slots_custom(self):
        self.client.force_login(self.admin)
        for i in range(3):
            self.assertIn("added", self.client.post("/config/workflow/stage/add/", {"label": f"E{i}"})["Location"])
        resp = self.client.post("/config/workflow/stage/add/", {"label": "E4"})
        self.assertIn("no_slot", resp["Location"])

    def test_edit_define_aprovador(self):
        self.client.force_login(self.admin)
        self.client.post("/config/workflow/stage/add/", {"label": "Diretoria"})
        stage = self.wf().stages.get(label="Diretoria")
        self.assertFalse(role_can(UserProfile.ROLE_ORCAMENTISTA, stage.approver_capability))
        resp = self.client.post("/config/workflow/stage/edit/", {
            "key": stage.key, "label": "Diretoria", "approver_role": UserProfile.ROLE_ORCAMENTISTA,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(role_can(UserProfile.ROLE_ORCAMENTISTA, stage.approver_capability))

    def test_remove_custom_ok_builtin_bloqueado(self):
        self.client.force_login(self.admin)
        self.client.post("/config/workflow/stage/add/", {"label": "Temp"})
        stage = self.wf().stages.get(label="Temp")
        resp = self.client.post("/config/workflow/stage/remove/", {"key": stage.key})
        self.assertIn("removed", resp["Location"])
        self.assertFalse(self.wf().stages.filter(key=stage.key).exists())
        # técnico built-in não removível
        resp = self.client.post("/config/workflow/stage/remove/", {"key": "technical"})
        self.assertIn("builtin", resp["Location"])
        self.assertTrue(self.wf().stages.filter(key="technical").exists())

    def test_move_troca_ordem(self):
        self.client.force_login(self.admin)
        self.client.post("/config/workflow/apply-template/", {"template": "tech_commercial"})
        wf = self.wf()
        tech = wf.stages.get(key="technical")
        comm = wf.stages.get(key="commercial")
        self.assertLess(tech.order, comm.order)
        resp = self.client.post("/config/workflow/stage/move/", {"key": "commercial", "direction": "up"})
        self.assertIn("reordered", resp["Location"])
        tech.refresh_from_db(); comm.refresh_from_db()
        self.assertLess(comm.order, tech.order)
