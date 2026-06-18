from decimal import Decimal
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Quotation, Customer
from apps.quotations.services import create_feixe_quotation

class FeatureViewsTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc2", password="123")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(company_name="Cliente Teste")

    def test_list_quotations(self):
        q = create_feixe_quotation(self.customer, "Feixe A")
        q.status = "sent"
        q.save()
        resp = self.client.get("/cotacoes/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Feixe A")
        self.assertContains(resp, "Cliente Teste")
        self.assertContains(resp, q.number)
        self.assertContains(resp, "Enviada")
        self.assertContains(resp, str(round(q.preco_com_impostos, 2)).replace(".", ","))
        
    def test_quotation_detail(self):
        q = create_feixe_quotation(self.customer, "Feixe A")
        resp = self.client.get(f"/cotacoes/{q.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Feixe A")
        self.assertContains(resp, q.number)
        self.assertContains(resp, "Estrutura Analítica")
        
    def test_quotation_revise_feixe(self):
        q = create_feixe_quotation(self.customer, "Feixe A")
        old_pk = q.pk
        old_num = q.number
        old_rev = q.revision
        resp = self.client.post(f"/cotacoes/{old_pk}/revisar/")
        self.assertEqual(resp.status_code, 302)
        
        q2 = Quotation.objects.get(pk=resp.url.split("/")[-2])
        self.assertNotEqual(q2.number, old_num)
        self.assertEqual(q2.revision, old_rev + 1)
        self.assertEqual(q2.customer, self.customer)
        self.assertEqual(q2.scope, "tube_bundle")
        self.assertEqual(q2.status, "draft")
        self.assertEqual(q2.title, "Feixe A")

    def test_quotation_revise_permutador(self):
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        resultado = quote_completo("BEU")
        q = create_permutador_quotation(self.customer, "BEU", {"designacao": "BEU", "n_tubos": 68}, resultado, title="BEU Test")
        
        resp = self.client.post(f"/cotacoes/{q.pk}/revisar/")
        self.assertEqual(resp.status_code, 302)
        
        q2 = Quotation.objects.get(pk=resp.url.split("/")[-2])
        self.assertNotEqual(q2.number, q.number)
        self.assertEqual(q2.revision, q.revision + 1)
        self.assertEqual(q2.customer, self.customer)
        self.assertEqual(q2.scope, "complete")
        self.assertEqual(q2.status, "draft")
