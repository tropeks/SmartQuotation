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

# NOTA: o markup sobre ensaios/transporte "depende do job" (PE Wellington, 2026-07-02)
# — não é regra fixa. Removido o teste que hardcodava "markup nunca sobre ensaios/transp".
# Default do motor volta a aplicar F.C. sobre o custo total (baseline validado -2,9%).
# Follow-up: toggle POR ORÇAMENTO p/ excluir ensaios/transporte do markup quando o job pedir.
