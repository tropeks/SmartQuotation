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
        dims = {
            "designacao": "BEU",
            "n_tubos": 68,
            "comprimento_tubo_mm": 6000,
            "od_tubo_mm": 19.05,
            "esp_tubo_mm": 1.65,
            "n_chicanas": 15,
            "comprimento_casco_mm": 6000,
            "diametro_casco_mm": 400,
            "esp_casco_mm": 6.35,
            "n_passes_tubos": 2,
            "rt_escopo": False,
            "classe_feixe": "TEMA C",
            "classe_casco": "TEMA C",
            "fluido_corrosivo": False,
            "fator_correcao_mo": 1.0
        }
        response = self.client.post("/api/permutador/estimate/", dims, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("custo_total", data)
        self.assertIn("custo_material", data)
        self.assertIn("custo_mao_obra", data)
        self.assertIn("custo_servicos", data)
        self.assertIn("preco_com_impostos", data)
        
        custo_total = data["custo_total"]
        # Aceite: custo_total ~128000 (±5%)
        self.assertTrue(128000 * 0.95 <= custo_total <= 128000 * 1.05, f"Custo total {custo_total} fora da margem")
