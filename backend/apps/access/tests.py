"""Testes do app apps.access (RBAC configurável)."""
from django.test import SimpleTestCase

from apps.access.capabilities import (
    CAPABILITIES,
    capability_codes,
    ensure_capabilities,
    is_known_capability,
)


class CapabilityRegistryTests(SimpleTestCase):
    def test_registry_nao_vazio(self):
        self.assertTrue(CAPABILITIES)

    def test_codes_unicos(self):
        codes = list(CAPABILITIES.keys())
        self.assertEqual(len(codes), len(set(codes)))

    def test_toda_entrada_tem_metadados(self):
        for code, meta in CAPABILITIES.items():
            self.assertTrue(code and isinstance(code, str), code)
            self.assertTrue(meta.get("label"), code)
            self.assertIn("description", meta, code)
            self.assertIn("category", meta, code)
            self.assertIn("is_dangerous", meta, code)
            self.assertIsInstance(meta["is_dangerous"], bool, code)

    def test_cobre_todas_capabilities_do_plano(self):
        # 1:1 com a tabela do F10_RBAC_CONFIG_PLAN.md (tuplas atuais das views)
        # + as capabilities aditivas do RBAC V2 M0 (PLAN_RBAC_V2_0_IMPL.md).
        esperadas = {
            "quotation.create",
            "quotation.write",
            "quotation.read",
            "quotation.price_api",
            "of.convert",
            "of.transition",
            "itp.manage",
            "approval.request_remote",
            "approval.request_presencial",
            "approval.panel_read",
            "cost_discovery.write",
            "rate.change",
            "rate.edit",
            "proposal.write",
            "tema_template.write",
            "material.read",
            "material.write",
            "nomus.reexport",
            "members.manage",
            "access.manage",
            # RBAC V2 M0 — slots de assinatura + gestão de papéis
            "approval.technical_sign",
            "approval.commercial_sign",
            "approval.quality_sign",
            "approval.custom_sign_1",
            "approval.custom_sign_2",
            "approval.custom_sign_3",
            "role.manage",
        }
        self.assertEqual(capability_codes(), esperadas)

    def test_is_known_capability(self):
        self.assertTrue(is_known_capability("of.convert"))
        self.assertFalse(is_known_capability("nope.unknown"))

    def test_ensure_capabilities_idempotente(self):
        primeiro = ensure_capabilities()
        segundo = ensure_capabilities()
        self.assertEqual(primeiro, segundo)
        self.assertEqual(primeiro, capability_codes())
