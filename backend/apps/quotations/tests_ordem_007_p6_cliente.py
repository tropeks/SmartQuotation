"""
Ordem 007 — P6: a revisão não troca o cliente. Bloqueado na rota `quotation_edit`
(Tier A), que é a única que aceita `customer_name` de um form numa revisão.
"""
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer, Quotation
from apps.quotations.services import create_feixe_quotation


class RevisaoNaoTrocaClienteTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="orc-p6", password="123")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=self.user, full_name="Orc P6", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(company_name="Cliente Original P6")
        self.outro = Customer.objects.create(company_name="Outro Cliente P6")

    def test_edit_bloqueia_troca_de_cliente(self):
        from apps.quotations.forms import FeixeDataSheetForm

        q = create_feixe_quotation(self.customer, "Feixe P6", created_by=self.user)
        data = FeixeDataSheetForm.initial_from_quotation(q)
        data = {k: ("" if v is None else v) for k, v in data.items()}
        data["customer_name"] = self.outro.company_name
        n_before = Quotation.objects.count()

        resp = self.client.post(reverse("quotations:edit", args=[q.pk]), data)

        self.assertEqual(resp.status_code, 200)   # re-renderiza com erro, não redireciona
        self.assertEqual(Quotation.objects.count(), n_before)   # NENHUMA revisão criada
        q.refresh_from_db()
        self.assertEqual(q.customer_id, self.customer.pk)   # cliente original intacto
