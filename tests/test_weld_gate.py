import pytest
import math
from pricing_engine.feixe_inputs import FeixeInputs, caso_136_tubos
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import engematex_seed

def test_weld_gate_solda_selagem_false():
    inp = FeixeInputs(solda_selagem=False)
    cot = quote_feixe(inp, engematex_seed())
    
    soma = 0.0
    for item in cot.itens:
        for op in item.operacoes + item.ensaios:
            if 'Passe de Raiz' in op.descricao or 'Passe de Acabamento' in op.descricao or 'L.P. Passe' in op.descricao:
                soma += op.custo
    assert soma == 0.0

def test_weld_gate_solda_selagem_true():
    inp = FeixeInputs(solda_selagem=True)
    cot = quote_feixe(inp, engematex_seed())
    
    soma = 0.0
    for item in cot.itens:
        for op in item.operacoes + item.ensaios:
            if 'Passe de Raiz' in op.descricao or 'Passe de Acabamento' in op.descricao or 'L.P. Passe' in op.descricao:
                soma += op.custo
    assert soma > 0.0

def test_weld_gate_caso_136_tubos():
    inp = caso_136_tubos()
    assert inp.solda_selagem is True
    
    cot = quote_feixe(inp, engematex_seed())
    
    assert abs(cot.custo_total - 34610.28) < 1.0
