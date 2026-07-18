"""UI dos knobs de custeio (Config de Engenharia V2). F1 deu a página + guard-rails; F2 mudou o
comportamento: knob sensível não aplica direto — vira PROPOSTA com dupla validação (SoD)."""
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.engineering_params.models import KnobChangeProposal, TenantParamConfig


class KnobsUITests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

    def _user(self, username, role):
        u = get_user_model().objects.create_user(username=username, password="x")
        extra = {"crea_number": f"CREA-{username}"} if role == UserProfile.ROLE_ENGENHEIRO else {}
        UserProfile.objects.create(user=u, full_name=username, role=role, **extra)
        return u

    def _login(self, username):
        self.client.login(username=username, password="x")

    # ── página ───────────────────────────────────────────────────────────────
    def test_pagina_renderiza_para_editor(self):
        self._user("adm", UserProfile.ROLE_ADMIN)
        self._login("adm")
        r = self.client.get("/engenharia/knobs/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "KNOBS DE CUSTEIO")
        self.assertContains(r, "espelho")
        self.assertContains(r, "tubos")
        self.assertContains(r, "Enviar para aprovação")   # F2: propõe, não "Salvar"

    # ── propor (F2: não aplica direto) ────────────────────────────────────────
    def test_save_cria_proposta_e_nao_aplica(self):
        self._user("adm", UserProfile.ROLE_ADMIN)
        self._login("adm")
        r = self.client.post("/engenharia/knobs/salvar/",
                             {"perda__espelho": "1.6", "setup__tubos": "0.35"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Proposta enviada")
        p = KnobChangeProposal.objects.get(status="pending")
        self.assertEqual(p.payload["perda_por_familia"]["after"]["espelho"], 1.6)
        # NÃO aplicou
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.perda_por_familia["espelho"], 1.4)
        # nenhuma auditoria de aplicação ainda
        self.assertFalse(AccessLog.objects.filter(action="param_change").exists())

    def test_save_nada_alterado_nao_cria_proposta(self):
        self._user("adm", UserProfile.ROLE_ADMIN)
        self._login("adm")
        cfg = TenantParamConfig.get_solo()
        r = self.client.post("/engenharia/knobs/salvar/",
                             {"perda__espelho": str(cfg.perda_por_familia["espelho"])})
        self.assertContains(r, "Nada alterado")
        self.assertEqual(KnobChangeProposal.objects.count(), 0)

    def test_orcamentista_nao_propoe(self):
        self._user("orc", UserProfile.ROLE_ORCAMENTISTA)
        self._login("orc")
        r = self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(KnobChangeProposal.objects.count(), 0)

    # ── aprovar (2ª validação) ────────────────────────────────────────────────
    def test_aprovar_por_outro_aplica_e_audita(self):
        self._user("adm", UserProfile.ROLE_ADMIN)
        gest = self._user("gest", UserProfile.ROLE_GESTOR_COMERCIAL)
        self._login("adm")
        self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        p = KnobChangeProposal.objects.get(status="pending")
        self._login("gest")
        r = self.client.post(f"/engenharia/knobs/aprovar/{p.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "aplicada")
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.6)
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "applied")
        self.assertTrue(AccessLog.objects.filter(action="param_change").exists())

    def test_sod_propositor_nao_ve_botao_nem_aprova(self):
        self._user("adm", UserProfile.ROLE_ADMIN)         # propositor (também qualificado)
        self._user("gest", UserProfile.ROLE_GESTOR_COMERCIAL)  # outro qualificado → SoD ativo
        self._login("adm")
        self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        p = KnobChangeProposal.objects.get(status="pending")
        # GET: propositor não vê "Aprovar e aplicar"
        r = self.client.get("/engenharia/knobs/")
        self.assertNotContains(r, "Aprovar e aplicar")
        self.assertContains(r, "aguardando um 2º aprovador")
        # POST aprovar a própria → serviço bloqueia (SoD), erro inline, segue pendente
        r = self.client.post(f"/engenharia/knobs/aprovar/{p.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Separação de funções")
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "pending")
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.4)

    def test_rejeitar_descarta_sem_aplicar(self):
        self._user("adm", UserProfile.ROLE_ADMIN)
        gest = self._user("gest", UserProfile.ROLE_GESTOR_COMERCIAL)
        self._login("adm")
        self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        p = KnobChangeProposal.objects.get(status="pending")
        self._login("gest")
        r = self.client.post(f"/engenharia/knobs/rejeitar/{p.pk}/")
        self.assertContains(r, "rejeitada")
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "rejected")
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.4)

    def test_orcamentista_nao_aprova(self):
        self._user("adm", UserProfile.ROLE_ADMIN)
        self._user("orc", UserProfile.ROLE_ORCAMENTISTA)
        self._login("adm")
        self.client.post("/engenharia/knobs/salvar/", {"perda__espelho": "1.6"})
        p = KnobChangeProposal.objects.get(status="pending")
        self._login("orc")
        r = self.client.post(f"/engenharia/knobs/aprovar/{p.pk}/")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "pending")
