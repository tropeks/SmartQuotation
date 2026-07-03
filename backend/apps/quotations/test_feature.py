from decimal import Decimal
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import CalculationSnapshot, Quotation, Customer
from apps.quotations.services import create_feixe_quotation

class FeatureViewsTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc2", password="123")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=self.user, full_name="Orc2", role=UserProfile.ROLE_ORCAMENTISTA)
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
        self.assertContains(resp, "COT-03")
        self.assertContains(resp, "Command Center")
        self.assertContains(resp, "g3-minimap")
        self.assertContains(resp, 'href="#sec-resumo"')
        self.assertContains(resp, 'id="sec-preco"')
        self.assertContains(resp, "Progresso da Cotação")
        self.assertContains(resp, "§1")
        self.assertContains(resp, "§6")
        
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
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q).count(), 1)
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q2).count(), 1)

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
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q).count(), 1)
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q2).count(), 1)

    def test_revise_permutador_reproduz_custo_original(self):
        """REGRESSÃO: revisar deve recomputar com as DIMENSÕES da cotação original, não o seed."""
        from apps.tema_templates.services import estimate_from_inputs
        from apps.quotations.services import create_permutador_quotation
        # dims customizadas (casco bem maior que o gabarito) → custo != seed
        cleaned = {"designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
                   "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 18,
                   "comprimento_casco_mm": 3000, "diametro_casco_mm": 1200, "esp_casco_mm": 16,
                   "n_passes_tubos": 2, "rt_escopo": "Total", "classe_feixe": "INOX",
                   "classe_casco": "CS", "fluido_corrosivo": "Tubos", "fator_correcao_mo": 1.0}
        resultado = estimate_from_inputs("BEU", cleaned)
        q = create_permutador_quotation(self.customer, "BEU", cleaned, resultado, title="BEU custom")
        resp = self.client.post(f"/cotacoes/{q.pk}/revisar/")
        q2 = Quotation.objects.get(pk=resp.url.split("/")[-2])
        # a revisão deve ter o MESMO preço (mesmas dims), não o preço do seed
        self.assertAlmostEqual(float(q2.preco_com_impostos), float(q.preco_com_impostos), delta=1.0)
