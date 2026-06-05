"""
Testes do app quotations + adapter pricing_engine.
Teste-chave: uma cotação persistida reproduz o gabarito ENGEMATEX (caso 136 tubos).
"""
from decimal import Decimal
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Quotation, Customer, QuotationItem, ItemMaterial, ItemOperation
from apps.quotations.adapter import recompute, default_inputs, to_feixe_inputs
from apps.quotations.services import create_feixe_quotation, next_number


class FeixeQuotationTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="Petrobras RPBC")

    def test_cotacao_persistida_reproduz_gabarito(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        # gabarito real ENGEMATEX: custo 35.353, preço c/imp 44.192 (gate ±10%)
        self.assertAlmostEqual(float(q.custo_total), 35353, delta=35353 * 0.10)
        self.assertAlmostEqual(float(q.preco_com_impostos), 44192, delta=44192 * 0.10)
        # custo = material + MO
        self.assertAlmostEqual(
            float(q.custo_total), float(q.custo_material + q.custo_mo), delta=1.0)

    def test_eap_persistida_com_roll_up(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        itens = QuotationItem.objects.filter(quotation=q)
        self.assertGreaterEqual(itens.count(), 8)        # tubos, espelhos, chicanas, montagem...
        # roll-up: soma dos itens == custo_total
        soma = sum((i.custo_total for i in itens), Decimal("0"))
        self.assertAlmostEqual(float(soma), float(q.custo_total), delta=1.0)
        # tubos têm matéria-prima persistida
        self.assertTrue(ItemMaterial.objects.filter(item__quotation=q, codigo_mp="TUB-01").exists())
        # furação tem operação persistida
        self.assertTrue(ItemOperation.objects.filter(item__quotation=q, codigo_op="OP-ESP-FURAR").exists())

    def test_peso_bruto_maior_que_liquido(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        self.assertGreater(q.peso_bruto_kg, q.peso_liquido_kg)   # refugo > 0
        self.assertGreater(q.perda_kg, 0)

    def test_parametrico_mais_tubos_aumenta_preco(self):
        q1 = create_feixe_quotation(self.customer, "136 tubos")
        inp = default_inputs(); inp["n_tubos"] = 200
        q2 = create_feixe_quotation(self.customer, "200 tubos", inputs=inp)
        self.assertGreater(q2.preco_com_impostos, q1.preco_com_impostos)

    def test_recompute_idempotente_nao_duplica_eap(self):
        q = create_feixe_quotation(self.customer, "Feixe")
        n1 = QuotationItem.objects.filter(quotation=q).count()
        recompute(q)                                     # recomputa
        n2 = QuotationItem.objects.filter(quotation=q).count()
        self.assertEqual(n1, n2)                          # snapshot substituído, não duplicado

    def test_numeracao_sequencial(self):
        q1 = create_feixe_quotation(self.customer, "A")
        q2 = create_feixe_quotation(self.customer, "B")
        self.assertTrue(q1.number.startswith("COT-"))
        self.assertNotEqual(q1.number, q2.number)
        self.assertEqual(int(q2.number.split("-")[-1]), int(q1.number.split("-")[-1]) + 1)

    def test_to_feixe_inputs_merge_defaults(self):
        q = Quotation(inputs={"n_tubos": 99}, customer=self.customer)
        inp = to_feixe_inputs(q)
        self.assertEqual(inp.n_tubos, 99)
        self.assertEqual(inp.tubo_material, "SA-179")    # default preservado


class DataSheetViewTests(TenantTestCase):
    """Slice end-to-end via HTTP: login -> data sheet -> recompute -> criar -> detalhe."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        self.client.force_login(self.user)

    def _form_data(self, **over):
        data = {
            "title": "Feixe 136 tubos", "customer_name": "Petrobras RPBC", "tipo": "TUBO RETO",
            "n_tubos": 136, "tubo_material": "SA-179", "tubo_od_spec": '3/4"',
            "tubo_wall_spec": "BWG 14", "tubo_comp_mm": 6096,
            "espelho_material": "SA-516 GR 70", "espelho_od_mm": 475,
            "espelho_flutuante_od_mm": 412, "espelho_esp_bruta_mm": 44.5,
            "chicana_qty": 18, "chicana_od_mm": 416.8, "chicana_esp_mm": 12.5,
            "chicana_cut_remaining_mm": 300, "tirante_qty": 12,
        }
        data.update(over)
        return data

    def test_data_sheet_carrega(self):
        resp = self.client.get("/cotacoes/nova/feixe/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preço de Venda")
        self.assertContains(resp, "design-system-g.css")

    def test_recompute_htmx_retorna_preco(self):
        resp = self.client.post("/cotacoes/recompute/", self._form_data())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preço de Venda")
        self.assertContains(resp, "price-line")

    def test_recompute_responde_a_mais_tubos(self):
        r136 = self.client.post("/cotacoes/recompute/", self._form_data(n_tubos=136))
        r200 = self.client.post("/cotacoes/recompute/", self._form_data(n_tubos=200))
        # extrai o preço grosso do HTML (presença de valores distintos)
        self.assertNotEqual(r136.content, r200.content)

    def test_criar_persiste_e_redireciona_pro_detalhe(self):
        resp = self.client.post("/cotacoes/criar/", self._form_data())
        self.assertEqual(resp.status_code, 302)
        q = Quotation.objects.latest("created_at")
        self.assertGreater(q.preco_com_impostos, 0)
        # detalhe renderiza a EAP + preço
        detalhe = self.client.get(resp.url)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, q.number)
        self.assertContains(detalhe, "Estrutura Analítica")

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get("/cotacoes/nova/feixe/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)
