"""Gate do CONTRATO de knobs configuráveis do motor (Config de Engenharia V2 / F1, Bloco A).

Os campos novos da TenantCostChain (perda_por_familia, setup_frac) são OVERRIDES por tenant das
constantes que hoje moram no motor. Este gate prova que:

  1. knobs VAZIOS não mudam nada — reproduzem os defaults de módulo, inclusive no caminho com
     dims_override (o único onde a perda por família é lida);
  2. o override de SETUP se CANCELA no referência (razão 1,0) → gate 0,0% do permutador intacto;
  3. o override de setup MOVE horas fora do referência, na direção certa (setup ↑ amortece a razão);
  4. o override de PERDA move o material SÓ no caminho com dims_override; sem override é inerte.

Motor PURO (stdlib) — roda no CI via `python -m tests.test_cost_chain_knobs`.
"""
import sys

from pricing_engine.beu_geometry import PERDA_POR_FAMILIA
from pricing_engine.permutador_quote import _SETUP_FRAC, quote_completo
from pricing_engine.rates import TenantCostChain

DESIG = "BEU"
# override de dimensões IDÊNTICAS ao seed (razão 1,0) → dispara o ramo de perda por família
# (espelho) sem mudar a geometria. 'ESPELHO FIXO' existe no seed BEU (familia 'espelho').
OVERRIDE_ESPELHO = {"ESPELHO FIXO": {"OD": 475, "ESP.": 34}}


def _chain(**kw):
    return TenantCostChain(fator_correcao_mo=1.0, **kw)


def test_perda_accessor_override_e_fallback():
    c = TenantCostChain(perda_por_familia={"espelho": 2.0})
    assert c.perda("espelho", 1.40) == 2.0        # override vence
    assert c.perda("tubo", 1.10) == 1.10          # sem override → default do ponto de uso
    assert TenantCostChain().perda("espelho", 1.40) == 1.40


def test_setup_accessor_override_e_fallback():
    c = TenantCostChain(setup_frac={"tubos": 0.9})
    assert c.setup("tubos", 0.20) == 0.9
    assert c.setup("solda", 0.10) == 0.10
    assert TenantCostChain().setup("tubos", 0.20) == 0.20


def test_knobs_vazios_reproduzem_o_default_de_modulo():
    """Chain SEM knobs == chain COM knobs iguais aos defaults de módulo — nos dois caminhos."""
    vazia = _chain()
    defaults = _chain(perda_por_familia=dict(PERDA_POR_FAMILIA), setup_frac=dict(_SETUP_FRAC))
    for ov, pr in [(None, None), (OVERRIDE_ESPELHO, None), (None, {"tubos": 2.0})]:
        a = quote_completo(DESIG, cost_chain=vazia, dims_override=ov, params=pr)
        b = quote_completo(DESIG, cost_chain=defaults, dims_override=ov, params=pr)
        assert a["custo_total"] == b["custo_total"], (ov, pr)


def test_setup_gate_safe_no_referencia():
    """Setup absurdo, mas razão 1,0 (params vazio) → MO idêntica: o setup se cancela."""
    base = quote_completo(DESIG, cost_chain=_chain())
    setupado = quote_completo(DESIG, cost_chain=_chain(setup_frac={k: 0.9 for k in _SETUP_FRAC}))
    assert setupado["custo_mao_obra"] == base["custo_mao_obra"]
    assert setupado["custo_total"] == base["custo_total"]


def test_setup_move_horas_fora_do_referencia():
    """Com razão 2,0 nos tubos: setup MAIOR amortece a razão → MENOS horas de MO."""
    params = {"tubos": 2.0}
    baixo = quote_completo(DESIG, cost_chain=_chain(setup_frac={"tubos": 0.2}), params=params)
    alto = quote_completo(DESIG, cost_chain=_chain(setup_frac={"tubos": 0.9}), params=params)
    assert alto["custo_mao_obra"] < baixo["custo_mao_obra"]


def test_perda_move_material_so_no_caminho_override():
    """COM dims_override do espelho: perda maior → mais peso bruto → mais custo de material.
    SEM override: a perda por família nunca é lida → inerte (gate 0,0% intacto)."""
    base = quote_completo(DESIG, cost_chain=_chain(), dims_override=OVERRIDE_ESPELHO)
    maior = quote_completo(DESIG, cost_chain=_chain(perda_por_familia={"espelho": 2.5}),
                           dims_override=OVERRIDE_ESPELHO)
    assert maior["custo_material"] > base["custo_material"]

    b0 = quote_completo(DESIG, cost_chain=_chain())
    m0 = quote_completo(DESIG, cost_chain=_chain(perda_por_familia={"espelho": 2.5}))
    assert m0["custo_material"] == b0["custo_material"]
    assert m0["custo_total"] == b0["custo_total"]


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    falhas = 0
    print("=" * 60)
    print("GATE — contrato de knobs configuráveis do motor")
    print("=" * 60)
    for t in tests:
        try:
            t()
            print(f"  OK     {t.__name__}")
        except AssertionError as e:
            falhas += 1
            print(f"  FALHOU {t.__name__}: {e}")
    print("=" * 60)
    print("GATE OK" if not falhas else f"GATE FALHOU ({falhas})")
    sys.exit(0 if not falhas else 1)


if __name__ == "__main__":
    main()
