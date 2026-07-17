"""
Teste ANTI-FLICKER (T5): o `can_convert` do render inicial (contexto de
`quotations.views.quotation_detail`) DEVE ser igual ao `can_convert` do poller de 5s
(`audit.views.convertibility_panel`), para CADA papel.

O `detail.html` faz `hx-get` a cada 5s para `audit:convertibility_panel`. Se as duas
views derivarem `can_convert` de fontes diferentes (p.ex. uma de tupla hardcoded e
outra de `user_can`), o botão "Converter em OF" pisca a cada poll. A garantia é a
FONTE ÚNICA: ambas chamam `user_can(user, "of.convert")`.

Usa TenantTestCase porque a matriz papel×capability (RolePermission) vive no schema.
"""
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.access.enforcement import user_can
from apps.access.matrix import ALL_ROLES, seed_access_matrix
from apps.audit import views as audit_views
from apps.quotations import views as quotation_views
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class ConvertFlickerParityTests(TestCase):
    def setUp(self):
        cache.clear()
        # Semeia a matriz default (tuplas atuais) no schema de teste.
        seed_access_matrix()
        self.factory = RequestFactory()
        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")

    def _user_for_role(self, role):
        user = User.objects.create_user(username=f"u-{role}", password="x-senha-123")
        extra = {}
        if role == UserProfile.ROLE_ENGENHEIRO:
            extra = {"crea_number": f"SP-{role}", "crea_state": "SP"}
        UserProfile.objects.create(user=user, full_name=role, role=role, **extra)
        return user

    def _capture_context(self, module, view, user, **kwargs):
        """Invoca `view` capturando o dict de contexto passado a `render`."""
        captured = {}

        def fake_render(request, template, context=None, *args, **kw):
            captured.update(context or {})
            return HttpResponse("ok")

        request = self.factory.get("/x")
        request.user = user
        with mock.patch.object(module, "render", side_effect=fake_render):
            view(request, **kwargs)
        return captured

    def test_can_convert_parity_render_vs_poller(self):
        for role in ALL_ROLES:
            with self.subTest(role=role):
                cache.clear()
                seed_access_matrix()  # cache foi limpo; garante matriz aquecida
                user = self._user_for_role(role)
                expected = user_can(user, "of.convert")

                # Render inicial: quotation_detail (quotation.read liberado a todos os papéis).
                ctx_detail = self._capture_context(
                    quotation_views,
                    quotation_views.quotation_detail,
                    user,
                    pk=self.quotation.pk,
                )
                self.assertEqual(ctx_detail["can_convert"], expected)

                # Poller: convertibility_panel (approval.panel_read). Papéis sem esse
                # acesso (viewer) nem disparam o poll — não há flicker possível.
                try:
                    ctx_panel = self._capture_context(
                        audit_views,
                        audit_views.convertibility_panel,
                        user,
                        pk=self.quotation.pk,
                    )
                except PermissionDenied:
                    continue

                self.assertEqual(ctx_panel["can_convert"], expected)
                # Fonte única: render inicial == poller.
                self.assertEqual(ctx_detail["can_convert"], ctx_panel["can_convert"])
