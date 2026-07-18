"""Serviço de propostas de knobs (Config Eng V2 / F2, Bloco B lite): SoD, escape auditado,
staleness e apply atômico."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.engineering_params.models import KnobChangeProposal, TenantParamConfig
from apps.engineering_params import knob_proposals as kp


class KnobProposalServiceTests(TestCase):
    def _user(self, username, role):
        u = get_user_model().objects.create_user(username=username, password="x")
        extra = {}
        if role == UserProfile.ROLE_ENGENHEIRO:
            extra["crea_number"] = f"CREA-{username}"   # engenheiro exige CREA (compliance RBAC)
        UserProfile.objects.create(user=u, full_name=username, role=role, **extra)
        return u

    def _eng(self, username="eng1"):
        return self._user(username, UserProfile.ROLE_ENGENHEIRO)

    # ── criação ────────────────────────────────────────────────────────────
    def test_create_captura_before_e_after(self):
        eng = self._eng()
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        self.assertEqual(p.status, "pending")
        self.assertEqual(p.payload["perda_por_familia"]["before"]["espelho"], 1.4)
        self.assertEqual(p.payload["perda_por_familia"]["after"]["espelho"], 1.6)
        # não aplicou ainda
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.4)

    def test_recusa_segunda_pendente(self):
        eng = self._eng()
        kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        with self.assertRaises(ValidationError):
            kp.create_proposal(eng, {"setup_frac": {"tubos": 0.3}})

    def test_create_sem_knob_sensivel_erra(self):
        eng = self._eng()
        with self.assertRaises(ValidationError):
            kp.create_proposal(eng, {"nao_existe": {"x": 1}})

    # ── aprovação / SoD ──────────────────────────────────────────────────────
    def test_aprovacao_por_outro_aplica_e_audita(self):
        eng = self._eng("eng1")
        aprovador = self._eng("eng2")
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6},
                                     "setup_frac": {"tubos": 0.3}})
        req = RequestFactory().post("/x")
        req.user = aprovador
        out = kp.approve_proposal(p.pk, aprovador, request=req)
        self.assertEqual(out.status, "applied")
        self.assertFalse(out.self_approved)
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.perda_por_familia["espelho"], 1.6)
        self.assertEqual(cfg.setup_frac["tubos"], 0.3)
        log = AccessLog.objects.filter(action="param_change").order_by("-id").first()
        self.assertEqual(log.metadata["proposal_id"], p.pk)
        self.assertFalse(log.metadata["self_approved"])

    def test_sod_bloqueia_autoaprovacao_com_outro_qualificado(self):
        eng = self._eng("eng1")
        self._eng("eng2")  # outro qualificado existe
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        with self.assertRaises(PermissionDenied):
            kp.approve_proposal(p.pk, eng)
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "pending")
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.4)

    def test_sod_escape_auditado_quando_unico_qualificado(self):
        eng = self._eng("eng1")  # único usuário qualificado
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        out = kp.approve_proposal(p.pk, eng)
        self.assertEqual(out.status, "applied")
        self.assertTrue(out.self_approved)
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.6)

    def test_aprovador_sem_capability_403(self):
        eng = self._eng("eng1")
        orc = self._user("orc", UserProfile.ROLE_ORCAMENTISTA)
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        with self.assertRaises(PermissionDenied):
            kp.approve_proposal(p.pk, orc)
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "pending")

    # ── staleness ────────────────────────────────────────────────────────────
    def test_staleness_recusa_se_config_mudou(self):
        eng = self._eng("eng1")
        aprovador = self._eng("eng2")
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        # alguém mexeu no valor vigente depois da proposta
        cfg = TenantParamConfig.get_solo()
        cfg.perda_por_familia = {**cfg.perda_por_familia, "espelho": 1.5}
        cfg.save()
        with self.assertRaises(ValidationError):
            kp.approve_proposal(p.pk, aprovador)
        self.assertEqual(KnobChangeProposal.objects.get(pk=p.pk).status, "pending")

    # ── rejeição ─────────────────────────────────────────────────────────────
    def test_reject_nao_muta_config(self):
        eng = self._eng("eng1")
        gestor = self._user("gestor", UserProfile.ROLE_GESTOR_COMERCIAL)
        p = kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.6}})
        out = kp.reject_proposal(p.pk, gestor)
        self.assertEqual(out.status, "rejected")
        self.assertEqual(TenantParamConfig.get_solo().perda_por_familia["espelho"], 1.4)
        # após rejeitar, pode criar nova proposta
        kp.create_proposal(eng, {"perda_por_familia": {"espelho": 1.7}})
