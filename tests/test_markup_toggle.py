"""Toggle de markup por job sobre ensaios/transporte (Wellington: caso a caso).

Baseline validado (-2,9%) aplica markup sobre o custo TOTAL. Wellington definiu
que markup sobre ensaios (END) e sobre transporte é decisão por orçamento, não
regra fixa. Estes testes travam:
  1. Default (flags True) = comportamento baseline intacto (markup sobre tudo).
  2. Flag False = aquela parcela vira pass-through (entra a custo, fora da base
     de markup); o preço cai exatamente pelo markup que incidia sobre ela.
"""
import math

from pricing_engine.wbs import Cotacao, Item, OperacaoExecutada
from pricing_engine.feixe_inputs import FeixeInputs
from pricing_engine.feixe_quote import quote_feixe


def _op_custo(cot, code_prefix):
    """Soma o custo de operações cujo código começa com code_prefix."""
    total = 0.0
    for it in cot.itens:
        for op in it.operacoes + it.ensaios:
            if op.codigo_op.startswith(code_prefix):
                total += op.custo
    return total


# ---- fórmula pura em wbs.Cotacao ----

def test_passthrough_zero_e_identico_ao_baseline():
    it = Item("MON-01", "x", operacoes=[OperacaoExecutada("OP-A", "a", custo_fixo=1000.0)])
    cot = Cotacao("C", "d", itens=[it], fator_preco=1.30, custo_passthrough=0.0)
    assert math.isclose(cot.preco_sem_impostos, 1000.0 * 1.30)


def test_passthrough_entra_a_custo_fora_da_base_de_markup():
    it = Item("MON-01", "x", operacoes=[OperacaoExecutada("OP-A", "a", custo_fixo=1000.0)])
    cot = Cotacao("C", "d", itens=[it], fator_preco=1.30, custo_passthrough=200.0)
    # base marcada = 1000-200=800 → *1.30 ; passthrough 200 entra a custo
    assert math.isclose(cot.preco_sem_impostos, 800.0 * 1.30 + 200.0)


# ---- integração via quote_feixe ----

def test_default_mantem_baseline():
    inp = FeixeInputs()
    assert inp.markup_sobre_ensaios is True
    assert inp.markup_sobre_transporte is True
    cot = quote_feixe(inp)
    assert math.isclose(cot.preco_sem_impostos, cot.custo_total * cot.fator_preco)


def test_transporte_off_vira_passthrough():
    base = quote_feixe(FeixeInputs())
    off = quote_feixe(FeixeInputs(markup_sobre_transporte=False))
    transp = _op_custo(base, "OP-TRANSP")
    assert transp > 0, "caso ref tem transporte > 0"
    # preço cai exatamente pelo markup que incidia sobre o transporte
    delta = base.preco_sem_impostos - off.preco_sem_impostos
    assert math.isclose(delta, transp * (base.fator_preco - 1.0), rel_tol=1e-9)
    assert math.isclose(off.custo_passthrough, transp, rel_tol=1e-9)


def test_ensaios_off_vira_passthrough_sem_incluir_transporte():
    base = quote_feixe(FeixeInputs())
    off = quote_feixe(FeixeInputs(markup_sobre_ensaios=False))
    # ensaios = grupo "ensaios" menos transporte; deve haver algo se inspecao_q
    assert off.custo_passthrough > 0
    # transporte NÃO deve entrar quando só ensaios está off
    transp = _op_custo(base, "OP-TRANSP")
    assert off.custo_passthrough < _op_custo(base, "OP-") or transp == 0
    delta = base.preco_sem_impostos - off.preco_sem_impostos
    assert math.isclose(delta, off.custo_passthrough * (base.fator_preco - 1.0), rel_tol=1e-9)
