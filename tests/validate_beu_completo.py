"""
Gate do motor BEU (permutador completo): falha se o custo total regredir > ±10% do
gabarito ENGEMATEX (R$ 128.160) ou se a geometria de algum material grande divergir > 15%
do peso da planilha.

Rodar: python -m tests.validate_beu_completo
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pricing_engine.beu_quote import quote_beu
from pricing_engine.beu_geometry import peso_liquido_geom

GABARITO_CUSTO = 128160.0
TOL_CUSTO = 0.10
TOL_GEOM = 0.15
SEEDS = os.path.join(ROOT, "pricing_engine", "seeds")


def _load(n):
    with open(os.path.join(SEEDS, n), encoding="utf-8") as f:
        return json.load(f)


def check_geometria():
    """Recalcula o peso líquido pela geometria e compara com a planilha (itens grandes)."""
    mats = _load("beu_materiais.json")["materiais"]
    erros = []
    checados = 0
    for m in mats:
        liq = peso_liquido_geom(m["familia"], m.get("dims", {}))
        if liq is None or not m.get("peso_liq"):
            continue
        qtd = float(m.get("dims", {}).get("QUANTIDADE", 1) or 1)
        calc_total = liq * qtd
        ref = m["peso_liq"]
        if ref < 5:  # ignora peças miúdas (peso irrelevante no custo)
            continue
        # placas de suporte são SEGMENTOS recortados (não disco cheio): a fórmula de
        # disco não se aplica — validadas como chicana, fora do gate geométrico estrito.
        if "SUPORTE" in (m["label"] or "").upper():
            continue
        checados += 1
        desvio = abs(calc_total - ref) / ref
        if desvio > TOL_GEOM:
            erros.append((m["label"], m["familia"], round(calc_total, 1), ref, f"{desvio:+.1%}"))
    return checados, erros


def main():
    print("=" * 72)
    print("VALIDAÇÃO — PERMUTADOR BEU COMPLETO (casco + cabeçote + feixe-U)")
    print("=" * 72)

    # 1) geometria dos materiais
    checados, gerros = check_geometria()
    print(f"\nGeometria de materiais: {checados} itens grandes checados, {len(gerros)} divergências >{TOL_GEOM:.0%}")
    for e in gerros:
        print(f"   ✗ {e[0]:24} ({e[1]}) calc={e[2]} kgf vs gabarito={e[3]} kgf ({e[4]})")

    # 2) custo total vs gabarito
    q = quote_beu()
    custo = q["custo_total"]
    delta = (custo - GABARITO_CUSTO) / GABARITO_CUSTO
    print(f"\nCusto por seção:")
    for s, v in sorted(q["por_secao"].items()):
        print(f"   {s:20} R$ {v:>12,.2f}")
    print(f"\n   Material  R$ {q['custo_material']:>12,.2f}")
    print(f"   Mão-obra  R$ {q['custo_mao_obra']:>12,.2f}")
    print(f"   Serviços  R$ {q['custo_servicos']:>12,.2f}")
    print(f"   {'─'*30}")
    print(f"   CUSTO TOTAL  R$ {custo:>11,.2f}   (gabarito R$ {GABARITO_CUSTO:,.0f})")
    print(f"   Δ vs gabarito: {delta:+.2%}")
    print(f"\n   Venda c/ impostos R$ {q['preco_com_impostos']:>12,.2f}   (gabarito R$ 160.200)")
    print(f"   Venda s/ impostos R$ {q['preco_sem_impostos']:>12,.2f}   (gabarito R$ 146.103)")

    ok = abs(delta) <= TOL_CUSTO and not gerros
    print("\n" + "=" * 72)
    if ok:
        print(f"GATE OK: custo Δ {delta:+.2%} dentro de ±{TOL_CUSTO:.0%}, geometria consistente.")
    else:
        motivos = []
        if abs(delta) > TOL_CUSTO:
            motivos.append(f"custo Δ {delta:+.2%} fora de ±{TOL_CUSTO:.0%}")
        if gerros:
            motivos.append(f"{len(gerros)} divergências de geometria")
        print(f"GATE FALHOU: {'; '.join(motivos)}")
    print("=" * 72)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
