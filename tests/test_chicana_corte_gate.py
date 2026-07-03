"""Gate da rota de corte da chicana: manual (default) vs laser (terceirizado).

Quando a chapa da chicana chega já cortada no perfil a LASER (serviço terceirizado),
as etapas de traçado/recorte/acabamento de contorno NÃO acontecem no chão de fábrica.
Furar (tubos), usinar, escarear, formar pacote e inspecionar continuam. Espelha o
padrão do gate solda_selagem (ver test_weld_gate.py). Ancorado no OF-3672 real: as 3
ops manuais somam exatamente o resíduo de MO (+2.040 → +14,5%) que sobra vs o orçamento.
"""
from pricing_engine.feixe_inputs import FeixeInputs
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import engematex_seed

# As 3 operações de corte/recorte de CONTORNO manual que o laser substitui.
_OPS_CORTE = {
    "Chicanas - Traçar e Recortar",
    "Chicanas - Traçar Recortes",
    "Chicanas - Recortar e Dar Acabamento",
}


def _custo_ops_corte(cot):
    return sum(
        op.custo
        for item in cot.itens
        for op in item.operacoes + item.ensaios
        if op.descricao in _OPS_CORTE
    )


def test_chicana_corte_manual_default():
    """Default = corte manual: as ops de traçado/recorte existem na MO."""
    inp = FeixeInputs()
    assert inp.chicana_corte_laser is False
    cot = quote_feixe(inp, engematex_seed())
    assert _custo_ops_corte(cot) > 0.0


def test_chicana_corte_laser_zera_recorte_manual():
    """Laser terceirizado: as 3 ops de contorno manual saem da MO."""
    inp = FeixeInputs(chicana_corte_laser=True)
    cot = quote_feixe(inp, engematex_seed())
    assert _custo_ops_corte(cot) == 0.0


def test_chicana_corte_laser_so_remove_o_recorte():
    """Laser NÃO mexe em furar/usinar/escarear: só o contorno sai; o resto da chicana fica."""
    base = quote_feixe(FeixeInputs(), engematex_seed())
    laser = quote_feixe(FeixeInputs(chicana_corte_laser=True), engematex_seed())
    mo_base = sum(it.custo_mo for it in base.itens)
    mo_laser = sum(it.custo_mo for it in laser.itens)
    # a diferença é EXATAMENTE o custo das 3 ops de contorno — nada mais muda
    assert abs((mo_base - mo_laser) - _custo_ops_corte(base)) < 0.01
    assert mo_laser < mo_base
