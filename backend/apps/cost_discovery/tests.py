"""
Testes do wizard de cadeia de custos (A1-c).
Teste-chave: back-solve calibra o fator de MO para reproduzir um preço REAL conhecido.
"""
from decimal import Decimal
from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.cost_discovery.models import CostDiscoverySession
from apps.cost_discovery import services
from apps.engineering_params.models import TenantParamConfig
from apps.materials.models import Material, MaterialPrice
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class BackSolveTests(TenantTestCase):
    def test_back_solve_reproduz_preco_conhecido(self):
        # alvo entre o mínimo e máximo do range → deve convergir com erro pequeno
        ref = {"n_tubos": 136}
        r = services.back_solve(ref, known_price=50000.0)
        self.assertLess(abs(r["error_pct"]), 1.0)          # erro < 1% (calibração precisa)
        self.assertGreater(r["fator"], 0)

    def test_run_back_solve_aplica_fator_no_tenant(self):
        s = CostDiscoverySession.objects.create(
            method="back_solve", reference_inputs={"n_tubos": 136},
            reference_known_price=Decimal("50000.00"))
        services.run_back_solve(s)
        s.refresh_from_db()
        self.assertIsNotNone(s.solved_fator_mo)
        # o fator calibrado foi aplicado ao config do tenant
        cfg = TenantParamConfig.get_solo()
        self.assertEqual(cfg.fator_correcao_mo, s.solved_fator_mo)

    def test_calibracao_afeta_cotacoes_seguintes(self):
        # calibra para um preço alto → cotação subsequente fica mais cara
        cust = Customer.objects.create(company_name="X")
        antes = create_feixe_quotation(cust, "antes")
        s = CostDiscoverySession.objects.create(
            method="back_solve", reference_inputs={"n_tubos": 136},
            reference_known_price=Decimal("60000.00"))
        services.run_back_solve(s)
        depois = create_feixe_quotation(cust, "depois")
        self.assertGreater(depois.preco_com_impostos, antes.preco_com_impostos)

    def test_top_down_grava_precos_e_fator(self):
        Material.objects.create(sigla="SA-179", tipo="AÇO CARBONO", densidade_kg_mm3=Decimal("0.00000785"))
        res = services.apply_top_down(
            [{"sigla": "SA-179", "forma": "tubo", "preco": "20.00"}], fator_mo=1.15)
        self.assertEqual(res["precos_gravados"], 1)
        self.assertTrue(MaterialPrice.objects.filter(material__sigla="SA-179", forma="tubo").exists())
        self.assertEqual(TenantParamConfig.get_solo().fator_correcao_mo, Decimal("1.1500"))

    def test_preco_material_do_tenant_dirige_a_cotacao(self):
        # grava tubo a R$30/kg (vs 13.5 default) → cotação fica mais cara
        Material.objects.create(sigla="SA-179", tipo="AÇO CARBONO", densidade_kg_mm3=Decimal("0.00000785"))
        cust = Customer.objects.create(company_name="X")
        antes = create_feixe_quotation(cust, "antes")
        services.apply_top_down([{"sigla": "SA-179", "forma": "tubo", "preco": "30.00"}])
        depois = create_feixe_quotation(cust, "depois")
        self.assertGreater(depois.custo_material, antes.custo_material)


class WizardViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="dono", password="senha-forte-123")
        self.client.force_login(self.user)

    def test_home_carrega(self):
        resp = self.client.get("/custos/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CADEIA DE CUSTOS")

    def test_back_solve_view_calibra(self):
        resp = self.client.post("/custos/calibrar/", {
            "n_tubos": "136", "tubo_material": "SA-179", "tubo_od_spec": '3/4"',
            "tubo_wall_spec": "BWG 14", "tubo_comp_mm": "6096", "espelho_od_mm": "475",
            "chicana_qty": "18", "known_price": "50000", "solve": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Fator de MO encontrado")
        self.assertTrue(CostDiscoverySession.objects.filter(method="back_solve").exists())

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get("/custos/")
        self.assertEqual(resp.status_code, 302)
