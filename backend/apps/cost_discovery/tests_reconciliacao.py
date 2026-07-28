"""
Calibração da MO ancorada na folha (S3).

O back_solve existente ancora no PREÇO de um job de referência. Como o preço vem de
benchmark e a mão de obra "não vai estar ok" (Wellington, 2026-07-16), o fator absorve
o erro do preço — o motor aprende a errar igual. Aqui a âncora é a folha de pagamento.
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase

from apps.cost_discovery.reconciliacao import (TOLERANCIA_PCT, horas_estimadas_de,
                                               limites_conhecidos, reconciliar)
from apps.quotations.models import Customer, ItemOperation, QuotationItem
from apps.quotations.services import create_feixe_quotation


class ContaTests(TenantTestCase):
    def test_fator_e_divisao_direta_sem_bissecao(self):
        """`fator_correcao_mo` multiplica horas linearmente, então inverte por divisão."""
        r = reconciliar(Decimal("2000"), Decimal("1200"))
        self.assertEqual(r.fator, Decimal("1.6667"))
        self.assertEqual(r.nivel, "subestima")

    def test_desvio_percentual_acompanha_o_fator(self):
        r = reconciliar(Decimal("1500"), Decimal("1000"))
        self.assertEqual(r.fator, Decimal("1.5000"))
        self.assertEqual(r.desvio_pct, Decimal("50.0"))

    def test_dentro_da_tolerancia_e_calibrado(self):
        r = reconciliar(Decimal("1020"), Decimal("1000"))
        self.assertEqual(r.nivel, "calibrado")
        self.assertLess(abs(r.desvio_pct), TOLERANCIA_PCT)

    def test_fabrica_gastou_menos_e_superestima(self):
        r = reconciliar(Decimal("800"), Decimal("1000"))
        self.assertEqual(r.nivel, "superestima")
        self.assertEqual(r.fator, Decimal("0.8000"))

    def test_sem_estimativa_nao_divide_por_zero(self):
        r = reconciliar(Decimal("2000"), Decimal("0"))
        self.assertEqual(r.nivel, "sem_estimativa")
        self.assertIsNone(r.fator)
        self.assertFalse(r.tem_resultado)

    def test_sem_folha_pede_o_dado(self):
        r = reconciliar(Decimal("0"), Decimal("1000"))
        self.assertEqual(r.nivel, "sem_folha")
        self.assertIsNone(r.fator)

    def test_entradas_nulas_nao_quebram(self):
        self.assertEqual(reconciliar(None, None).nivel, "sem_estimativa")

    def test_os_limites_saem_junto_do_numero(self):
        """Fator sem limites vira verdade absoluta na cabeça de quem lê."""
        limites = limites_conhecidos()
        self.assertEqual(len(limites), 3)
        self.assertTrue(any("agregado" in l.lower() for l in limites))
        self.assertTrue(any("ociosidade" in l.lower() for l in limites))


class HorasEstimadasTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="Cliente S3")

    def test_soma_hh_e_hm_da_eap_persistida(self):
        q = create_feixe_quotation(self.customer, "Feixe S3")
        esperado = sum(
            (op.horas_hh + op.horas_hm
             for op in ItemOperation.objects.filter(item__quotation=q, aplicavel=True)),
            Decimal("0"))

        self.assertEqual(horas_estimadas_de([q]), esperado)
        self.assertGreater(esperado, 0, "a fixture precisa ter horas")

    def test_operacao_nao_aplicavel_fica_de_fora(self):
        """Operação marcada como não aplicável não consome hora da fábrica."""
        q = create_feixe_quotation(self.customer, "Feixe S3")
        antes = horas_estimadas_de([q])

        item = QuotationItem.objects.filter(quotation=q).first()
        ItemOperation.objects.create(
            item=item, codigo_op="OP-FANTASMA", descricao="Não aplicável",
            custo_direto=False, aplicavel=False,
            horas_hh=Decimal("999.00"), horas_hm=Decimal("0.00"),
            taxa_hora=Decimal("100.00"), taxa_hora_hm=Decimal("0.00"),
            custo=Decimal("0.00"))

        self.assertEqual(horas_estimadas_de([q]), antes)

    def test_periodo_sem_cotacao_devolve_zero(self):
        self.assertEqual(horas_estimadas_de([]), Decimal("0"))

    def test_aceita_queryset_alem_de_lista(self):
        from apps.quotations.models import Quotation

        create_feixe_quotation(self.customer, "Feixe S3")
        pelo_queryset = horas_estimadas_de(Quotation.objects.all())
        pela_lista = horas_estimadas_de(list(Quotation.objects.all()))
        self.assertEqual(pelo_queryset, pela_lista)
        self.assertGreater(pelo_queryset, 0)


class FluxoCompletoTests(TenantTestCase):
    def test_da_eap_ao_fator(self):
        """O caminho inteiro: EAP real → horas estimadas → fator contra a folha."""
        customer = Customer.objects.create(company_name="Cliente Fluxo")
        q = create_feixe_quotation(customer, "Feixe Fluxo")
        estimadas = horas_estimadas_de([q])

        # A fábrica pagou o dobro do que o sistema previu.
        r = reconciliar(estimadas * 2, estimadas)

        self.assertEqual(r.fator, Decimal("2.0000"))
        self.assertEqual(r.nivel, "subestima")
        self.assertIn("margem", r.texto)
