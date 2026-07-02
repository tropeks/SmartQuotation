import pytest

from pricing_engine.feixe_inputs import FeixeInputs, caso_136_tubos
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import engematex_seed


def test_default_custo_transporte_preserva_gabarito():
    inp = caso_136_tubos()
    assert inp.custo_transporte == 1600.0

    cot = quote_feixe(inp, engematex_seed())

    assert abs(cot.custo_total - 34610.28) < 1.0


def test_custo_transporte_reduz_custo_total_em_exatamente_a_diferenca():
    inp_default = caso_136_tubos()
    inp_custom = FeixeInputs(custo_transporte=800.0)

    cot_default = quote_feixe(inp_default, engematex_seed())
    cot_custom = quote_feixe(inp_custom, engematex_seed())

    assert abs((cot_default.custo_total - cot_custom.custo_total) - 800.0) < 1e-6


def test_markup_nao_se_aplica_a_ensaios_e_transporte():
    inp = caso_136_tubos()
    # Usamos o seed que carrega o fator_preco padrão (ex: 1.20)
    cot = quote_feixe(inp, engematex_seed())
    
    custo_end_total = sum(it.custo_end for it in cot.itens)
    custo_base = cot.custo_total - custo_end_total
    
    preco_esperado = (custo_base * cot.fator_preco) + custo_end_total
    
    assert abs(cot.preco_sem_impostos - preco_esperado) < 1e-6
