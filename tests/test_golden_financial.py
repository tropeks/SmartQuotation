"""Validação FINANCEIRA dos Golden Cases contra as âncoras REAIS (Wellington).

Diferente de test_golden_cases_of.py (snapshot: trava o output do motor contra
ele mesmo), aqui a âncora é o VALOR REAL do orçamento fechado, transcrito em
tests/golden_anchors.json. Gate beta do PE: |delta| <= 10% (hard-fail), <= 5% ideal.

Estado atual (2026-07-03): o motor de FEIXE não reproduz o OF-3672 por subtotal —
MP -52,8% (subprecifica material) e MO +45,5% (superprecifica mão-de-obra) quase se
anulam no total (-14,9%). Esses três ass: são xfail(strict) = alvo de calibração
explícito; quando a calibração fechar, viram xpass e este arquivo avisa pra remover
o marcador. O OF-3683 (permutador custom inox, ~6x BEU) ainda não tem seed no motor
→ backtest pendente (skip documentado), mas a âncora fica registrada e guardada.
"""
import json
import math
import pathlib

import pytest

from pricing_engine.feixe_inputs import caso_of_3672
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import engematex_seed

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
    return quote_feixe(caso_of_3672(), engematex_seed())


@pytest.mark.xfail(strict=True, reason="MP -52,8%: motor subprecifica material (seed R$/kg "
                   "defasado + caso_of_3672 mínimo, componentes em default). Calibração pendente.")
def test_of3672_MP_dentro_do_gate():
    real = _ANCHORS["OF-3672"]["subtotais"]["MP"]
    mp = sum(it.custo_material for it in _cot_3672().itens)
    assert abs(_delta_pct(mp, real)) <= GATE_HARD_PCT


@pytest.mark.xfail(strict=True, reason="MO +45,5%: motor superprecifica mao-de-obra (set default "
                   "cheio nos drivers default). Calibração pendente.")
def test_of3672_MO_dentro_do_gate():
    real = _ANCHORS["OF-3672"]["subtotais"]["MO"]
    mo = sum(it.custo_mo for it in _cot_3672().itens)
    assert abs(_delta_pct(mo, real)) <= GATE_HARD_PCT


@pytest.mark.xfail(strict=True, reason="custo total -14,9%: erros de MP e MO se cancelam "
                   "parcialmente; o total 'perto' e enganoso. Calibração pendente.")
def test_of3672_custo_total_dentro_do_gate():
    real = _ANCHORS["OF-3672"]["custo_total"]
    assert abs(_delta_pct(_cot_3672().custo_total, real)) <= GATE_HARD_PCT


# ---- OF-3683 (permutador) — âncora registrada, backtest pendente de seed ----

@pytest.mark.skip(reason="OF-3683 e permutador custom (E-51303, inox, ~6x BEU) sem seed no motor. "
                  "Backtest exige seed novo ou mapeamento TEMA + escala. Âncora ja registrada.")
def test_of3683_backtest_permutador():
    raise NotImplementedError("pendente de seed do permutador OF-3683")
