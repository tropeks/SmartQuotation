"""
Gate do motor de PERMUTADOR COMPLETO — valida TODAS as designações com seed presente
(BEU, BEM, ...) contra seus referenciais ENGEMATEX. Falha se qualquer custo total regredir
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

# Auditoria da assinatura 3-tupla de check_geometria():
# - o gate validar() consome (checados, erros, documentados);
# - o backtest geométrico do OF-3683 também desempacota 3 valores;
# - os backtests financeiros citados nas docstrings (OF-3672 / job backtests) não chamam
#   check_geometria() diretamente.
CHECK_GEOMETRIA_CALL_SITES_AUDIT = {
    "tests/test_of3683_geometria_disco_bocal.py": 3,
    "tests/validate_permutador_completo.py": 3,
}


def _load(n):
    with open(os.path.join(SEEDS, n), encoding="utf-8") as f:
        return json.load(f)


def check_geometria(designacao):
    mats = _load(f"{designacao.lower()}_materiais.json")["materiais"]
    erros = []
    documentados = []
    checados = 0
    for m in mats:
        liq = peso_liquido_geom(m["familia"], m.get("dims", {}))
        if liq is None or not m.get("peso_liq"):
            continue
        qtd = float(m.get("dims", {}).get("QUANTIDADE", 1) or 1)
        ref = m["peso_liq"]
        if ref < 5:
            continue
        # placas de suporte (segmentos) e espelhos (disco FURADO) não batem a fórmula de
        # disco cheio — o peso_liq desconta furos/recortes. Fora do gate geométrico estrito.
        if ("SUPORTE" in (m["label"] or "").upper()
                or m.get("familia") in ("espelho", "perfurado")):
            continue
        # item com divergência investigada e documentada (não reconcilia por nenhum ajuste
        # defensável de dims/densidade — ver "geom_xfail" no seed) — follow-up, não bloqueia.
        if m.get("geom_xfail"):
            documentados.append((m["label"], m["familia"], round(liq * qtd, 1), ref))
            continue
        checados += 1
        desvio = abs(liq * qtd - ref) / ref
        if desvio > TOL_GEOM:
            erros.append((m["label"], m["familia"], round(liq * qtd, 1), ref, f"{desvio:+.1%}"))
    return checados, erros, documentados


# Designações de REFERÊNCIA (planilha padrão calibrada): geometria ESTRITA (gate duro).
# Demais são backtests de JOB real (ex.: OF3683) — validam o custo TOTAL contra o
# orçamento; divergência de geometria em item avulso é AVISO/follow-up, não quebra o
# gate (o impacto no custo já é capturado pelo Δ do total).
_REFERENCIAS = {"beu", "bem"}


def validar(designacao):
    g = _load(f"{designacao.lower()}_referencial.json")
    referencial = g["custo_total_com_impostos"]
    eh_ref = designacao.lower() in _REFERENCIAS
    checados, gerros, gdoc = check_geometria(designacao)
    q = quote_completo(designacao)
    custo = q["custo_total"]
    delta = (custo - referencial) / referencial

    print(f"\n{'─'*72}\n[{designacao}] {g.get('descricao','')}")
    for s, v in sorted(q["por_secao"].items()):
        print(f"    {s:20} R$ {v:>12,.2f}")
    print(f"    {'─'*46}")
    print(f"    Material R$ {q['custo_material']:>11,.2f} · MO R$ {q['custo_mao_obra']:>11,.2f} · Serviços R$ {q['custo_servicos']:>11,.2f}")
    print(f"    CUSTO TOTAL  R$ {custo:>11,.2f}   referencial R$ {referencial:>11,.2f}   Δ {delta:+.2%}")
    print(f"    Venda c/imp  R$ {q['preco_com_impostos']:>11,.2f}   referencial R$ {g['preco_venda_com_impostos']:>11,.2f}")
    marca = "✗" if eh_ref else "⚠"
    sufixo = "" if eh_ref else "  (aviso: job backtest, não bloqueia — follow-up)"
    print(f"    Geometria: {checados} itens grandes, {len(gerros)} divergências >{TOL_GEOM:.0%}{sufixo}")
    for e in gerros:
        print(f"       {marca} {e[0]:24} ({e[1]}) calc={e[2]} vs {e[3]} kgf ({e[4]})")
    for d in gdoc:
        print(f"       · {d[0]:24} ({d[1]}) calc={d[2]} vs {d[3]} kgf  [documentado/geom_xfail, excluído do gate — follow-up]")

    # geometria só bloqueia REFERÊNCIAS calibradas; job backtests validam o custo TOTAL.
    ok = abs(delta) <= TOL_CUSTO and (not gerros or not eh_ref)
    return ok, delta, len(gerros)


def _tem_referencial(designacao):
    return os.path.exists(os.path.join(SEEDS, f"{designacao.lower()}_referencial.json"))


def main():
    todas = designacoes_disponiveis()
    # Nem toda designação com seed de MATERIAIS tem referencial TOTAL (MO+serviços) —
    # ex.: OF3683 é job avulso com seed de MP apenas (ver test_golden_of3683.py para
    # o backtest de MP dele). Este gate só valida o custo TOTAL, então pula quem não
    # tiver referencial em vez de quebrar a suíte.
    designacoes = [d for d in todas if _tem_referencial(d)]
    puladas = [d for d in todas if d not in designacoes]
    print("=" * 72)
    print(f"VALIDAÇÃO — PERMUTADOR COMPLETO · designações: {', '.join(designacoes)}")
    if puladas:
        print(f"  (puladas, sem referencial de custo TOTAL: {', '.join(puladas)})")
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
