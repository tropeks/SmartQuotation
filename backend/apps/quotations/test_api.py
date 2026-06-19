from django_tenants.test.cases import TenantTestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation

class QuotationAPITests(TenantTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="123")
        self.client = APIClient(HTTP_HOST=self.get_test_tenant_domain())
        self.client.force_authenticate(user=self.user)
        self.customer = Customer.objects.create(company_name="Test Customer")

    def test_get_cotacoes_list(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        response = self.client.get("/api/cotacoes/")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIsInstance(data, list) # Assuming unpaginated or paginate response? Wait, viewset defaults to standard pagination or not? We'll check.
        # usually data is list if no pagination, or dict with 'results' if paginated. Let's handle both.
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["number"], q.number)
        self.assertIn("preco_com_impostos", results[0])
        self.assertAlmostEqual(float(results[0]["preco_com_impostos"]), float(q.preco_com_impostos), places=2)
        # check nested items
        self.assertIn("itens", results[0])
        self.assertTrue(len(results[0]["itens"]) > 0)

    def test_post_permutador_estimate(self):
        base = {
            "designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
            "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 18,
            "comprimento_casco_mm": 1631, "diametro_casco_mm": 764, "esp_casco_mm": 9.5,
            "n_passes_tubos": 2, "rt_escopo": "Total", "classe_feixe": "CS",
            "classe_casco": "CS", "fluido_corrosivo": "Tubos", "fator_correcao_mo": 1.0,
        }
        r = self.client.post("/api/permutador/estimate/", base, format='json')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("custo_total", "custo_material", "custo_mao_obra", "custo_servicos",
                  "preco_com_impostos"):
            self.assertIn(k, d)
        self.assertGreater(d["custo_total"], 50000)        # custo plausível p/ um BEU
        # a API RESPONDE às dimensões: casco maior → custo maior (não devolve o seed fixo)
        maior = {**base, "comprimento_casco_mm": 3000, "diametro_casco_mm": 1200,
                 "esp_casco_mm": 16}
        r2 = self.client.post("/api/permutador/estimate/", maior, format='json')
        self.assertEqual(r2.status_code, 200)
        self.assertGreater(r2.json()["custo_total"], d["custo_total"] + 10000)
