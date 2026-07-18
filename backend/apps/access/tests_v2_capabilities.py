"""
RBAC V2 — M0. Garante que as capabilities novas de assinatura de estágio + role.manage
estão no registry E na DEFAULT_MATRIX com os defaults corretos. Puro (SimpleTestCase, sem DB).

M0 é ADITIVO: as capabilities entram no catálogo e na matriz, mas ainda NÃO são enforced
(nenhum require_capability as referencia). O gate técnico CREA atual não muda — technical_sign
só passa a valer com o trait requires_crea em M1.
"""
from django.test import SimpleTestCase

from apps.accounts.models import UserProfile
from apps.access.capabilities import CAPABILITIES, ensure_capabilities
from apps.access.matrix import DEFAULT_MATRIX

E = UserProfile.ROLE_ENGENHEIRO
G = UserProfile.ROLE_GESTOR_COMERCIAL
A = UserProfile.ROLE_ADMIN

_NEW_CODES = [
    "approval.technical_sign",
    "approval.commercial_sign",
    "approval.quality_sign",
    "approval.custom_sign_1",
    "approval.custom_sign_2",
    "approval.custom_sign_3",
    "role.manage",
]


class RbacV2M0CapabilitiesTests(SimpleTestCase):
    def test_novos_codes_no_registry(self):
        for code in _NEW_CODES:
            self.assertIn(code, CAPABILITIES, f"{code} ausente do registry")

    def test_novos_codes_marcados_is_dangerous(self):
        # Assinaturas e gestão de papéis são sensíveis → sinalizadas na grade.
        for code in _NEW_CODES:
            self.assertTrue(CAPABILITIES[code]["is_dangerous"], f"{code} deveria ser is_dangerous")

    def test_registry_integro(self):
        # ensure_capabilities valida labels/categories/unicidade; não pode quebrar.
        self.assertEqual(ensure_capabilities(), set(CAPABILITIES.keys()))

    def test_defaults_da_matriz(self):
        # Defaults conservadores — espelham o aprovador atual e evitam concessão surpresa.
        self.assertEqual(DEFAULT_MATRIX["approval.technical_sign"], frozenset({E}))
        self.assertEqual(DEFAULT_MATRIX["approval.commercial_sign"], frozenset({G, A}))
        self.assertEqual(DEFAULT_MATRIX["approval.quality_sign"], frozenset({A}))
        for slot in ("approval.custom_sign_1", "approval.custom_sign_2", "approval.custom_sign_3"):
            self.assertEqual(DEFAULT_MATRIX[slot], frozenset({A}))
        self.assertEqual(DEFAULT_MATRIX["role.manage"], frozenset({A}))

    def test_technical_sign_nao_concede_admin_por_default(self):
        # A assinatura técnica exige engenheiro (compliance CREA); admin NÃO entra por default
        # — a dupla-condição com requires_crea (M1) é o que fecha isso.
        self.assertNotIn(A, DEFAULT_MATRIX["approval.technical_sign"])

    def test_matriz_e_registry_em_sincronia(self):
        # O mesmo invariante do assert de módulo, explícito como teste.
        self.assertEqual(set(DEFAULT_MATRIX.keys()), set(CAPABILITIES.keys()))
