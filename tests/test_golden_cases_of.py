"""
Suite de regressão dos golden cases reais OF-3672 (REPLAN, feixe tubular reto) e
OF-3399 (REFAP, feixe tubular U) — orçamentos manuscritos reais que também são a fonte
dos aliases de material cobertos por tests/test_material_alias.py (B.3003H14, A-266
etc.) e do valor de custo_transporte=800.0 usado em tests/test_transporte_input.py.

Diferente de caso_136_tubos (calibrado -2,9% vs um referencial estruturado em planilha),
estes dois casos vêm de rascunhos manuscritos onde só um subconjunto dos campos é
legível com confiança (ver docstrings de caso_of_3672/caso_of_3399 em feixe_inputs.py).
Por isso os testes de cotação aqui são de REGRESSÃO/SNAPSHOT (travam o valor atual do
motor para os inputs conhecidos, sem inventar um referencial financeiro que o rascunho não
permite confirmar), não uma validação ±X% contra o total do orçamento real.
"""
from pricing_engine.feixe_inputs import caso_of_3672, caso_of_3399
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import engematex_seed


def test_caso_of_3672_inputs_refletem_o_orcamento_real():
    inp = caso_of_3672()
    assert inp.n_tubos == 210
    assert inp.tubo_comp_mm == 3048.0
    assert inp.custo_transporte == 800.0
    assert inp.tipo == "TUBO RETO"


def test_caso_of_3672_cotacao_snapshot():
    # guarda de regressão pura (seed genérico). A VALIDAÇÃO FINANCEIRA real (vs orçamento
    # 40.756 com preços reais do job) está em tests/test_golden_financial.py.
    inp = caso_of_3672()
    cot = quote_feixe(inp, engematex_seed())
    # 27600.53 = 29640.53 − 2040 (chicana_corte_laser=True remove as 3 ops de contorno manual)
    assert abs(cot.custo_total - 27600.53) < 1.0


def test_caso_of_3399_inputs_refletem_o_orcamento_real():
    inp = caso_of_3399()
    assert inp.tipo == "TUBO U"
    assert inp.is_u is True
    assert inp.n_tubos == 64
    assert inp.tubo_comp_mm == 13000.0
    assert inp.tubo_material == "B.3003H14"


def test_caso_of_3399_cotacao_snapshot():
    inp = caso_of_3399()
    cot = quote_feixe(inp, engematex_seed())
    assert abs(cot.custo_total - 31407.55) < 1.0
