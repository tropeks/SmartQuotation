"""
Ordem 007 — P1: a listagem de cotações mostra só a revisão VIGENTE (maior `revision` do
mesmo `number`); o histórico das revisões fica no detalhe (ver views.quotation_detail).
"""
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class IsCurrentRevisionTests(TenantTestCase):
    """P1/P2 — `services.is_current_revision`."""

    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME Vigente")

    def test_unica_revisao_e_vigente(self):
        from apps.quotations.services import is_current_revision
        q = create_feixe_quotation(self.customer, "Feixe")
        self.assertTrue(is_current_revision(q))

    def test_revisao_antiga_deixa_de_ser_vigente(self):
        from apps.quotations.adapter import revise_feixe
        from apps.quotations.services import is_current_revision

        orig = create_feixe_quotation(self.customer, "Feixe")
        nova = revise_feixe(orig, created_by=None)
        orig.refresh_from_db()
        self.assertFalse(is_current_revision(orig))
        self.assertTrue(is_current_revision(nova))


class ListagemMostraApenasVigenteTests(TenantTestCase):
    """P1 — a listagem de cotações mostra só a revisão vigente (max revision por number)."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="orc-p1", password="123")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=self.user, full_name="Orc P1", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(company_name="ACME P1")

    def test_lista_so_a_revisao_vigente_do_numero(self):
        from apps.quotations.adapter import revise_feixe

        orig = create_feixe_quotation(self.customer, "Feixe P1")
        nova = revise_feixe(orig, created_by=None)

        resp = self.client.get("/cotacoes/")
        self.assertEqual(resp.status_code, 200)
        numeros_na_pagina = [row["obj"].pk for row in resp.context["quotations"]]
        self.assertIn(nova.pk, numeros_na_pagina)
        self.assertNotIn(orig.pk, numeros_na_pagina)   # revisão superada NÃO aparece
