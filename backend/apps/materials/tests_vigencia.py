"""
Preço vigente: uma resolução só, determinística.

A mesma pergunta — "qual preço vale hoje?" — estava respondida em três lugares
(`materials/views.py`, `quotations/adapter.py`, `cost_discovery/services.py`) e as
respostas divergiam. As duas do custeio iteravam SEM `order_by` e deixavam o último
registro do queryset vencer: com duas vigências válidas na mesma data, qual preço
entrava no orçamento dependia da ordem que o Postgres devolvesse as linhas.

Preço de material é a maior parcela do custo de um feixe. Indeterminismo aqui é preço
errado sem ninguém perceber.
"""
from datetime import date, timedelta
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase

from apps.materials.models import Material, MaterialPrice


class PrecoVigenteTests(TenantTestCase):
    def setUp(self):
        self.material = Material.objects.create(
            sigla="A-516.60", tipo="AÇO CARBONO", densidade_kg_mm3="0.0000078500")
        self.hoje = date.today()

    def _preco(self, valor, valid_from, valid_until=None):
        return MaterialPrice.objects.create(
            material=self.material, forma="chapa", preco_brl_kg=str(valor),
            valid_from=valid_from, valid_until=valid_until)

    def test_vence_a_vigencia_mais_recente(self):
        """Criando a NOVA primeiro: sem ordenação explícita, a antiga sobrescrevia."""
        nova = self._preco("12.00", self.hoje - timedelta(days=10))
        self._preco("7.00", self.hoje - timedelta(days=90))

        vigente = MaterialPrice.objects.vigente(self.material, "chapa")
        self.assertEqual(vigente.pk, nova.pk, "o preço mais recente é que vale")

    def test_ignora_vigencia_futura(self):
        atual = self._preco("10.00", self.hoje - timedelta(days=5))
        self._preco("99.00", self.hoje + timedelta(days=30))

        self.assertEqual(MaterialPrice.objects.vigente(self.material, "chapa").pk, atual.pk)

    def test_ignora_vigencia_encerrada(self):
        self._preco("5.00", self.hoje - timedelta(days=90),
                    valid_until=self.hoje - timedelta(days=30))
        atual = self._preco("10.00", self.hoje - timedelta(days=10))

        self.assertEqual(MaterialPrice.objects.vigente(self.material, "chapa").pk, atual.pk)

    def test_sem_preco_vigente_devolve_none(self):
        self._preco("5.00", self.hoje + timedelta(days=10))
        self.assertIsNone(MaterialPrice.objects.vigente(self.material, "chapa"))

    def test_desempata_pelo_mais_recente_criado(self):
        """Duas vigências no MESMO dia: vence a cadastrada por último."""
        self._preco("8.00", self.hoje)
        segunda = self._preco("9.00", self.hoje)

        self.assertEqual(MaterialPrice.objects.vigente(self.material, "chapa").pk,
                         segunda.pk)

    def test_consulta_em_data_passada(self):
        """Reproduzir uma cotação antiga exige o preço que valia naquele dia."""
        antigo = self._preco("5.00", date(2026, 1, 1), valid_until=date(2026, 5, 31))
        self._preco("10.00", date(2026, 6, 1))

        self.assertEqual(
            MaterialPrice.objects.vigente(self.material, "chapa", on_date=date(2026, 3, 1)).pk,
            antigo.pk)

    def test_mapa_de_vigentes_traz_um_por_material_e_forma(self):
        outro = Material.objects.create(sigla="A-240.304", tipo="AÇO INOX",
                                       densidade_kg_mm3="0.0000080000")
        self._preco("12.00", self.hoje - timedelta(days=10))
        self._preco("7.00", self.hoje - timedelta(days=90))
        MaterialPrice.objects.create(material=outro, forma="tubo", preco_brl_kg="40.00",
                                     valid_from=self.hoje)

        mapa = MaterialPrice.objects.mapa_vigente()

        self.assertEqual(mapa[("A-516.60", "chapa")], Decimal("12.00"))
        self.assertEqual(mapa[("A-240.304", "tubo")], Decimal("40.00"))
        self.assertEqual(len(mapa), 2, "um preço por (material, forma)")


class CosteioUsaOPrecoCertoTests(TenantTestCase):
    """A cadeia de custos que alimenta o motor tem de ver o mesmo preço da tela."""

    def test_cadeia_de_custos_pega_a_vigencia_mais_recente(self):
        from apps.quotations.adapter import build_cost_chain
        from apps.quotations.models import Customer, Quotation

        material = Material.objects.create(sigla="A-516.60", tipo="AÇO CARBONO",
                                           densidade_kg_mm3="0.0000078500")
        hoje = date.today()
        MaterialPrice.objects.create(material=material, forma="chapa",
                                     preco_brl_kg="12.00",
                                     valid_from=hoje - timedelta(days=10))
        MaterialPrice.objects.create(material=material, forma="chapa",
                                     preco_brl_kg="7.00",
                                     valid_from=hoje - timedelta(days=90))

        cliente = Customer.objects.create(company_name="Cliente Preço")
        q = Quotation.objects.create(number="COT-PRECO", customer=cliente,
                                     title="Preço", scope="tube_bundle", inputs={})

        chain = build_cost_chain(q)

        self.assertEqual(chain.material_price[("A-516.60", "chapa")], 12.0,
                         "o motor tem de custear com o preço vigente, não com o sorteado")
