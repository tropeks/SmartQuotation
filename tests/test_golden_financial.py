"""Validação FINANCEIRA dos Golden Cases contra as âncoras REAIS (Wellington).

Diferente de test_golden_cases_of.py (snapshot: trava o output do motor contra
ele mesmo), aqui a âncora é o VALOR REAL do orçamento fechado, transcrito em
tests/golden_anchors.json. Gate beta do PE: |delta| <= 10% (hard-fail), <= 5% ideal.

Estado (2026-07-03): OF-3672 CALIBRADO. Com a transcrição real do manuscrito (mandrilado
sem solda de selagem, 10 chicanas cortadas a laser, espelhos A-266 gr.2 forjado) + os
preços R$/kg reais do job, o motor bate o TOTAL a +3,5% (banda ideal <=5%) e a MP a -3,5%
— ambos VERDES. Resta a MO a +14,5% (xfail documentado): o job terceirizou o corte das
chicanas a LASER, routing que o motor modela como recorte manual. O OF-3683 (permutador
custom inox, ~6x BEU) agora tem seed completo (pricing_engine/seeds/of3683_materiais.json,
54 itens de MP + of3683_operacoes.json, 205 linhas de MO + 9 itens lump-sum do resumo) —
backtest de MP, MO e TOTAL em tests/test_golden_of3683.py: MP delta ~0,0016%, MO delta
~-0,56%, TOTAL delta ~+0,15% (todos VERDES, dentro da banda ideal).
"""
import json
import math
import pathlib

import pytest

from pricing_engine.feixe_inputs import caso_of_3672
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import engematex_seed


def _chain_3672():
    """Cadeia de custos com os preços R$/kg REAIS do job OF-3672 (no produto viriam da
    tabela MaterialPrice do tenant). Tubo pequeno SA-179 ~R$28/kg; espelho A-266 gr.2
    FORJADO ~R$55/kg (caro); chapa CS ~R$7/kg; inox 304 ~R$50/kg. Deriva do orçamento real."""
    ch = engematex_seed()
    ch.material_price.update({
        ("SA-179", "tubo"): 28.0, ("A-179", "tubo"): 28.0,
        ("A-266 GR 2", "disco"): 55.0, ("A-266 GR 2", "chapa"): 55.0,
        ("SA-516 GR 60", "chapa"): 7.0, ("A-516 GR 60", "chapa"): 7.0,
        ("A-36", "chapa"): 7.0, ("SA-36", "chapa"): 7.0,
        ("INOX 304", "chapa"): 50.0, ("AISI-304", "chapa"): 50.0,
    })
    return ch

_ANCHORS = json.loads((pathlib.Path(__file__).parent / "golden_anchors.json").read_text())

GATE_HARD_PCT = 10.0   # falha dura acima disso (beta PE)


def _delta_pct(motor, real):
    return (motor / real - 1.0) * 100.0


# ---- integridade das âncoras (guarda o dado transcrito) ----

@pytest.mark.parametrize("of", ["OF-3672", "OF-3683"])
def test_ancora_subtotais_somam_o_total(of):
    a = _ANCHORS[of]
    soma = sum(a["subtotais"].values())
    # tolerância de 1,5% cobre arredondamento de leitura de manuscrito
    assert math.isclose(soma, a["custo_total"], rel_tol=0.015), (
        f"{of}: subtotais somam {soma:,.0f} vs total {a['custo_total']:,.0f}")


def test_ancoras_tem_pv_maior_que_custo():
    for of, a in _ANCHORS.items():
        if of.startswith("_"):
            continue
        assert a["PV"] > a["custo_total"], f"{of}: PV deve cobrir o custo"


# ---- backtest financeiro OF-3672 (feixe) vs âncora real ----

def _cot_3672():
    return quote_feixe(caso_of_3672(), _chain_3672())


def test_of3672_custo_total_dentro_do_gate():
    """VALIDAÇÃO FINANCEIRA principal: o total do motor bate no orçamento real (+3,5%,
    dentro da banda IDEAL <=5%). Com a transcrição real (mandrilado, 10 chicanas laser,
    espelho A-266 forjado) + preços reais do job."""
    real = _ANCHORS["OF-3672"]["custo_total"]
    assert abs(_delta_pct(_cot_3672().custo_total, real)) <= GATE_HARD_PCT


def test_of3672_MP_dentro_do_gate():
    """MP -3,5%: a geometria do motor × preços reais reproduz a matéria-prima real."""
    real = _ANCHORS["OF-3672"]["subtotais"]["MP"]
    mp = sum(it.custo_material for it in _cot_3672().itens)
    assert abs(_delta_pct(mp, real)) <= GATE_HARD_PCT


def test_of3672_MO_dentro_do_gate():
    """MO ~0%: com o routing laser-vs-manual modelado (chicana_corte_laser=True no caso),
    o corte de contorno das chicanas sai da MO (chapas cortadas a LASER, terceirizado) e o
    motor bate a MO real. As 3 ops de traçado/recorte manual somavam exatamente o resíduo
    de +14,5% que sobrava antes (ver tests/test_chicana_corte_gate.py)."""
    real = _ANCHORS["OF-3672"]["subtotais"]["MO"]
    mo = sum(it.custo_mo for it in _cot_3672().itens)
    assert abs(_delta_pct(mo, real)) <= GATE_HARD_PCT


# ---- OF-3683 (permutador) — seed completo + backtest MP/MO/TOTAL em tests/test_golden_of3683.py ----
#
# Seeds criados (pricing_engine/seeds/of3683_materiais.json, 54 itens de MP das páginas
# 1-2; of3683_operacoes.json, 205 linhas de MO das páginas 3-8 + 9 itens lump-sum do
# resumo da página 8) e validados via quote_completo("of3683", ...). Ver
# tests/test_golden_of3683.py: MP delta ~0,0016%, MO delta ~-0,56%, TOTAL delta ~+0,15%
# — todos dentro da banda ideal (<=5%).
