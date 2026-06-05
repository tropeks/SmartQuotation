"""
Gate do motor de PERMUTADOR COMPLETO — valida TODAS as designações com seed presente
(BEU, BEM, ...) contra seus gabaritos ENGEMATEX. Falha se qualquer custo total regredir
> ±10% ou se a geometria de algum material grande divergir > 15% do peso da planilha.

Rodar: python -m tests.validate_permutador_completo
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pricing_engine.permutador_quote import quote_completo, designacoes_disponiveis
from pricing_engine.beu_geometry import peso_liquido_geom

TOL_CUSTO = 0.10
TOL_GEOM = 0.15
SEEDS = os.path.join(ROOT, "pricing_engine", "seeds")


def _load(n):
    with open(os.path.join(SEEDS, n), encoding="utf-8") as f:
        return json.load(f)


def check_geometria(designacao):
    mats = _load(f"{designacao.lower()}_materiais.json")["materiais"]
    erros = []
    checados = 0
    for m in mats:
        liq = peso_liquido_geom(m["familia"], m.get("dims", {}))
        if liq is None or not m.get("peso_liq"):
            continue
        qtd = float(m.get("dims", {}).get("QUANTIDADE", 1) or 1)
        ref = m["peso_liq"]
        if ref < 5:
            continue
        # placas de suporte são SEGMENTOS recortados (não disco cheio): fora do gate.
        if "SUPORTE" in (m["label"] or "").upper():
            continue
        checados += 1
        desvio = abs(liq * qtd - ref) / ref
        if desvio > TOL_GEOM:
            erros.append((m["label"], m["familia"], round(liq * qtd, 1), ref, f"{desvio:+.1%}"))
    return checados, erros


def validar(designacao):
    g = _load(f"{designacao.lower()}_ground_truth.json")
    gabarito = g["custo_total_com_impostos"]
    checados, gerros = check_geometria(designacao)
    q = quote_completo(designacao)
    custo = q["custo_total"]
    delta = (custo - gabarito) / gabarito

    print(f"\n{'─'*72}\n[{designacao}] {g.get('descricao','')}")
    for s, v in sorted(q["por_secao"].items()):
        print(f"    {s:20} R$ {v:>12,.2f}")
    print(f"    {'─'*46}")
    print(f"    Material R$ {q['custo_material']:>11,.2f} · MO R$ {q['custo_mao_obra']:>11,.2f} · Serviços R$ {q['custo_servicos']:>11,.2f}")
    print(f"    CUSTO TOTAL  R$ {custo:>11,.2f}   gabarito R$ {gabarito:>11,.2f}   Δ {delta:+.2%}")
    print(f"    Venda c/imp  R$ {q['preco_com_impostos']:>11,.2f}   gabarito R$ {g['preco_venda_com_impostos']:>11,.2f}")
    print(f"    Geometria: {checados} itens grandes, {len(gerros)} divergências >{TOL_GEOM:.0%}")
    for e in gerros:
        print(f"       ✗ {e[0]:24} ({e[1]}) calc={e[2]} vs {e[3]} kgf ({e[4]})")

    ok = abs(delta) <= TOL_CUSTO and not gerros
    return ok, delta, len(gerros)


def main():
    designacoes = designacoes_disponiveis()
    print("=" * 72)
    print(f"VALIDAÇÃO — PERMUTADOR COMPLETO · designações: {', '.join(designacoes)}")
    print("=" * 72)
    resultados = [(d, *validar(d)) for d in designacoes]
    todas_ok = all(r[1] for r in resultados)
    print("\n" + "=" * 72)
    for d, ok, delta, ng in resultados:
        print(f"  {d}: {'OK' if ok else 'FALHOU'}  (custo Δ {delta:+.2%}, {ng} div. geom.)")
    print("GATE OK" if todas_ok else "GATE FALHOU")
    print("=" * 72)
    sys.exit(0 if todas_ok else 1)


if __name__ == "__main__":
    main()
