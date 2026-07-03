"""Guarda de regressão do cross-check de geometria do OF-3683 (permutador ELEKEIROZ
E-51303) para os 3 itens de casco_material que divergiam >15% do peso_bruto do
manuscrito antes desta correção:

  - DISCO BOCAL (IT.4) e (IT.6): "CHAPA Φ<OD>X<ESP>" (DES 17.263-04-2) — recortados de
    retalho QUADRADO de chapa 316L, não de um blank redondo (diferente do
    espelho/tampo). O peso_bruto do manuscrito reconcilia com o quadrado envolvente
    OD×OD, não com o círculo (π/4·OD²) — família dedicada 'disco_bocal' em
    pricing_engine/beu_geometry.py (peso_disco_bocal), sem tocar a família 'disco'
    usada pelos espelhos/tampos (que reconciliam via CÍRCULO e quebrariam se a fórmula
    global mudasse — ver DISCO BOCAL (IT.5), abaixo do piso de checagem mas mesma
    família, e os espelhos feixe_material que continuam via 'disco').
  - CHAPA (IT.37): reconciliada com ESP=9.525mm (3/8") por back-solve, fechando o
    peso_bruto do manuscrito (17.277 kgf) perfeitamente (desvio < 1%).
"""
import pytest

from pricing_engine.beu_geometry import peso_liquido_geom
from tests.validate_permutador_completo import TOL_GEOM, check_geometria, _load

_DISCO_BOCAL_LABELS = {"DISCO BOCAL (IT.4)", "DISCO BOCAL (IT.5)", "DISCO BOCAL (IT.6)"}


def _item(label):
    mats = _load("of3683_materiais.json")["materiais"]
    for m in mats:
        if m["label"] == label:
            return m
    raise AssertionError(f"item {label!r} não encontrado no seed")


@pytest.mark.parametrize("label", sorted(_DISCO_BOCAL_LABELS))
def test_disco_bocal_usa_familia_dedicada(label):
    m = _item(label)
    assert m["familia"] == "disco_bocal"


@pytest.mark.parametrize("label", sorted(_DISCO_BOCAL_LABELS))
def test_disco_bocal_reconcilia_peso_bruto(label):
    """calc (quadrado envolvente OD×OD × ESP) vs peso_bruto do manuscrito, <=15%."""
    m = _item(label)
    liq = peso_liquido_geom(m["familia"], m["dims"])
    qtd = float(m["dims"].get("QUANTIDADE", 1) or 1)
    ref = m["peso_bruto"]
    desvio = abs(liq * qtd - ref) / ref
    assert desvio <= TOL_GEOM, f"{label}: calc={liq*qtd:.2f} vs peso_bruto={ref} ({desvio:+.1%})"


def test_chapa_it37_reconcilia_peso_bruto():
    """IT.37 reconcilia com ESP=9.525mm via back-solve."""
    m = _item("CHAPA (IT.37)")
    assert not m.get("geom_xfail"), "IT.37 não deveria mais estar marcada com geom_xfail"
    liq = peso_liquido_geom(m["familia"], m["dims"])
    qtd = float(m["dims"].get("QUANTIDADE", 1) or 1)
    desvio = abs(liq * qtd - m["peso_bruto"]) / m["peso_bruto"]
    assert desvio <= TOL_GEOM, "IT.37 deve reconciliar o peso"


def test_of3683_zero_divergencias_geometria_no_gate():
    """Gate consolidado: com disco_bocal (IT.4/IT.6) e CHAPA (IT.37) reconciliando,
    check_geometria não deve mais reportar nenhuma divergência >15% para o OF-3683."""
    _checados, erros, documentados = check_geometria("of3683")
    assert erros == []
    assert not any(d[0] == "CHAPA (IT.37)" for d in documentados)
