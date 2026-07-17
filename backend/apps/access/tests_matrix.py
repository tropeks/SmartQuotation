"""
Testes da DEFAULT_MATRIX + seed (T4).

Prova que, após semear, role_can(role, cap) == (role in tupla default) para TODA
combinação, e que o seed é idempotente. TenantTestCase: RolePermission é por schema.
"""
from django.core.cache import cache

from django_tenants.test.cases import TenantTestCase as TestCase

from apps.access.capabilities import CAPABILITIES
from apps.access.enforcement import invalidate_matrix_cache, role_can
from apps.access.matrix import ALL_ROLES, DEFAULT_MATRIX, seed_access_matrix
from apps.access.models import RolePermission


class DefaultMatrixSeedTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_cobre_o_catalogo(self):
        self.assertEqual(set(DEFAULT_MATRIX.keys()), set(CAPABILITIES.keys()))

    def test_seed_cria_uma_linha_por_celula(self):
        result = seed_access_matrix()
        esperado = len(CAPABILITIES) * len(ALL_ROLES)
        self.assertEqual(result["created"], esperado)
        self.assertEqual(RolePermission.objects.count(), esperado)

    def test_role_can_bate_com_a_tupla(self):
        seed_access_matrix()
        invalidate_matrix_cache()
        for cap in CAPABILITIES:
            for role in ALL_ROLES:
                esperado = role in DEFAULT_MATRIX[cap]
                self.assertEqual(role_can(role, cap), esperado, f"{role}×{cap}")

    def test_orcamentista_nao_converte_of(self):
        seed_access_matrix()
        invalidate_matrix_cache()
        self.assertFalse(role_can("orcamentista", "of.convert"))
        self.assertTrue(role_can("engenheiro", "of.convert"))

    def test_seed_idempotente(self):
        seed_access_matrix()
        segundo = seed_access_matrix()
        self.assertEqual(segundo["created"], 0)
        self.assertEqual(
            RolePermission.objects.count(), len(CAPABILITIES) * len(ALL_ROLES)
        )

    def test_seed_nao_sobrescreve_customizacao(self):
        seed_access_matrix()
        # Admin customiza: concede of.convert ao orcamentista.
        rp = RolePermission.objects.get(role="orcamentista", capability="of.convert")
        rp.allowed = True
        rp.save()
        # Reexecutar o seed NÃO deve reverter a customização.
        seed_access_matrix()
        rp.refresh_from_db()
        self.assertTrue(rp.allowed)
