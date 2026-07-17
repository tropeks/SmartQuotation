"""
Testes de enforcement (T3): role_can / user_can / require_capability + cache.

Usa TenantTestCase porque RolePermission é model de TENANT (vive no schema).
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.access.enforcement import (
    invalidate_matrix_cache,
    require_capability,
    role_can,
    user_can,
)
from apps.access.models import RolePermission


def _view(request, *args, **kwargs):
    return HttpResponse("ok")


class RoleCanTests(TestCase):
    def setUp(self):
        cache.clear()
        # Slate limpo: a migration 0002 pré-semeia a matriz no schema; estes
        # testes gerenciam suas próprias linhas.
        RolePermission.objects.all().delete()
        RolePermission.objects.create(
            role=UserProfile.ROLE_ENGENHEIRO, capability="of.convert", allowed=True
        )
        RolePermission.objects.create(
            role=UserProfile.ROLE_ORCAMENTISTA, capability="of.convert", allowed=False
        )

    def test_permitido(self):
        self.assertTrue(role_can(UserProfile.ROLE_ENGENHEIRO, "of.convert"))

    def test_negado_por_allowed_false(self):
        self.assertFalse(role_can(UserProfile.ROLE_ORCAMENTISTA, "of.convert"))

    def test_negado_sem_linha(self):
        self.assertFalse(role_can(UserProfile.ROLE_VIEWER, "of.convert"))

    def test_capability_desconhecida_e_false(self):
        self.assertFalse(role_can(UserProfile.ROLE_ENGENHEIRO, "cap.inexistente"))

    def test_role_none_e_false(self):
        self.assertFalse(role_can(None, "of.convert"))

    def test_cache_invalidado_no_save(self):
        # Aquece o cache com o estado atual (viewer não pode).
        self.assertFalse(role_can(UserProfile.ROLE_VIEWER, "of.convert"))
        # Concede -> o signal post_save deve invalidar o cache.
        RolePermission.objects.create(
            role=UserProfile.ROLE_VIEWER, capability="of.convert", allowed=True
        )
        self.assertTrue(role_can(UserProfile.ROLE_VIEWER, "of.convert"))

    def test_invalidate_manual(self):
        self.assertTrue(role_can(UserProfile.ROLE_ENGENHEIRO, "of.convert"))
        invalidate_matrix_cache()
        self.assertTrue(role_can(UserProfile.ROLE_ENGENHEIRO, "of.convert"))


class UserCanTests(TestCase):
    def setUp(self):
        cache.clear()
        RolePermission.objects.all().delete()
        RolePermission.objects.create(
            role=UserProfile.ROLE_ENGENHEIRO, capability="of.convert", allowed=True
        )
        self.eng = User.objects.create_user(username="eng", password="x-senha-123")
        UserProfile.objects.create(
            user=self.eng,
            full_name="Eng",
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="SP-1",
            crea_state="SP",
        )
        self.orc = User.objects.create_user(username="orc", password="x-senha-123")
        UserProfile.objects.create(
            user=self.orc, full_name="Orc", role=UserProfile.ROLE_ORCAMENTISTA
        )

    def test_user_com_papel_permitido(self):
        self.assertTrue(user_can(self.eng, "of.convert"))

    def test_user_com_papel_negado(self):
        self.assertFalse(user_can(self.orc, "of.convert"))

    def test_staff_sem_profile_e_false(self):
        staff = User.objects.create_user(
            username="staff", password="x-senha-123", is_staff=True
        )
        self.assertFalse(user_can(staff, "of.convert"))


class RequireCapabilityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        RolePermission.objects.all().delete()
        RolePermission.objects.create(
            role=UserProfile.ROLE_ENGENHEIRO, capability="of.convert", allowed=True
        )
        self.eng = User.objects.create_user(username="eng", password="x-senha-123")
        UserProfile.objects.create(
            user=self.eng,
            full_name="Eng",
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="SP-1",
            crea_state="SP",
        )
        self.orc = User.objects.create_user(username="orc", password="x-senha-123")
        UserProfile.objects.create(
            user=self.orc, full_name="Orc", role=UserProfile.ROLE_ORCAMENTISTA
        )

    def _req(self, user):
        req = self.factory.get("/x")
        req.user = user
        return req

    def test_anonimo_redireciona_login(self):
        from django.contrib.auth.models import AnonymousUser

        wrapped = require_capability("of.convert")(_view)
        resp = wrapped(self._req(AnonymousUser()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_sem_permissao_403(self):
        wrapped = require_capability("of.convert")(_view)
        with self.assertRaises(PermissionDenied):
            wrapped(self._req(self.orc))

    def test_com_permissao_passa(self):
        wrapped = require_capability("of.convert")(_view)
        resp = wrapped(self._req(self.eng))
        self.assertEqual(resp.status_code, 200)

    def test_staff_bypass_com_allow_platform_staff(self):
        staff = User.objects.create_user(
            username="staff", password="x-senha-123", is_staff=True
        )
        wrapped = require_capability("of.convert", allow_platform_staff=True)(_view)
        resp = wrapped(self._req(staff))
        self.assertEqual(resp.status_code, 200)

    def test_staff_sem_flag_e_403(self):
        staff = User.objects.create_user(
            username="staff2", password="x-senha-123", is_staff=True
        )
        wrapped = require_capability("of.convert")(_view)
        with self.assertRaises(PermissionDenied):
            wrapped(self._req(staff))
