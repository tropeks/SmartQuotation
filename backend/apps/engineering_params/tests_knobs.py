"""UI dos knobs de custeio (Config de Engenharia V2 / F1, Bloco C): página, save auditado,
faixa min/max em modo warn e gate de RBAC."""
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.engineering_params.models import TenantParamConfig


class KnobsUITests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

    def _login(self, role):
        User = get_user_model()
        u = User.objects.create_user(username=f"u_{role}", password="x")
        UserProfile.objects.create(user=u, full_name=role, role=role)
        self.client.login(username=f"u_{role}", password="x")
        return u

    def test_pagina_renderiza_para_editor(self):
        self._login(UserProfile.ROLE_ADMIN)
        r = self.client.get("/engenharia/knobs/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "KNOBS DE CUSTEIO")
        self.assertContains(r, "espelho")     # scrap por família
        self.assertContains(r, "tubos")       # setup por parâmetro

    def test_save_persiste_os_knobs(self):
        self._login(UserProfile.ROLE_ADMIN)
        r = self.client.post("/engenharia/knobs/salvar/",
                             {"perda__espelho": "1.6", "setup__tubos": "0.35"})
        self.assertEqual(r.status_code, 200)
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.perda_por_familia["espelho"], 1.6)
        self.assertEqual(cfg.setup_frac["tubos"], 0.35)
        # chaves não enviadas ficam intactas
        self.assertIn("perfurado", cfg.perda_por_familia)

    def test_save_audita_param_change_com_diff(self):
        self._login(UserProfile.ROLE_ADMIN)
        self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        log = AccessLog.objects.filter(action="param_change").order_by("-id").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata["knob"], "config_engenharia_v2")
        self.assertEqual(log.metadata["anterior"]["perda_por_familia"]["espelho"], 1.4)
        self.assertEqual(log.metadata["novo"]["perda_por_familia"]["espelho"], 1.6)

    def test_fora_da_faixa_avisa_mas_salva(self):
        """Faixa segura do espelho = 1,40 ±50% = [0,70; 2,10]. 2,5 está fora → avisa, mas salva."""
        self._login(UserProfile.ROLE_ADMIN)
        r = self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "2.5"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "fora da faixa")                 # warn no partial re-renderizado
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 2.5)  # salvou

    def test_entrada_invalida_mantem_valor(self):
        self._login(UserProfile.ROLE_ADMIN)
        self.client.post("/engenharia/knobs/salvar/",
                         {"perda__espelho": "abc", "perda__perfurado": "0"})  # inválido e ≤0
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.perda_por_familia["espelho"], 1.4)      # mantido
        self.assertEqual(cfg.perda_por_familia["perfurado"], 1.4)    # mantido

    def test_orcamentista_nao_edita(self):
        self._login(UserProfile.ROLE_ORCAMENTISTA)
        r = self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.4)  # não mudou
