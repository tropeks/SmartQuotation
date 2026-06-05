"""
Motor de custeio do PERMUTADOR COMPLETO (designação TEMA BEU: bonnet + casco 1 passe +
feixe em U). Compõe matéria-prima (peso geométrico × preço) + operações (horas × rate,
escaladas pelo fator de correção de MO) + serviços/terceiros (custo fixo), e forma o preço.

Estrutura analítica por seção (reconcilia com o gabarito ENGEMATEX = R$ 128.160):
  feixe (tubos-U, espelho, chicanas, tirantes, barras, alças) ·
  casco (virolas, tampo, flange principal, bocais, anéis, pedestais, suporte) ·
  cabeçote (virola, tampo, chapa divisora, flange, bocais) ·
  finalização (inspeção dimensional, teste hidrostático, data book, ferramentas, consumíveis)

quote_beu(cost_chain) → dict com custo por seção, custo total e preço de venda.
A cadeia de custos do tenant (rates.TenantCostChain) sobrescreve o fator de MO e os
preços de material por kgf — exatamente como em feixe_quote. Sem ela, usa os defaults
ENGEMATEX embutidos no seed (validados ao gabarito real).
"""
from __future__ import annotations
import json
import os

from .beu_geometry import peso_liquido_geom

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")


def _load(nome):
    with open(os.path.join(_SEEDS, nome), encoding="utf-8") as f:
        return json.load(f)


def _norm_mat(material):
    """Normaliza nome de material p/ casar com a cadeia de custos (ex.: 'SA-516 GR 70')."""
    return (material or "").strip().upper()


# família geométrica → forma de matéria-prima (chave da TenantCostChain.material_price)
_FAMILIA_FORMA = {
    "tubo": "tubo", "pipe": "tubo", "chapa_retangular": "chapa",
    "disco": "chapa", "tampo_2_1": "chapa", "anel": "forjado",
    "flange_wn": "forjado",
}


def quote_beu(cost_chain=None, fator_correcao_mo: float = 1.0,
              fator_preco: float = 1.25, impostos_pct: float = 9.0,
              dims_override: dict | None = None) -> dict:
    """Calcula o custo e o preço do permutador BEU completo.

    cost_chain: opcional. Se tiver `.fator_correcao_mo`, escala TODAS as horas de MO.
        Se tiver `.material_price(material)` (ou price_kgf), sobrescreve o preço por kgf.
    fator_correcao_mo: usado se cost_chain não trouxer o fator.
    dims_override: {label_material: {dim: valor}} para recálculo geométrico de peso
        (what-if paramétrico). Sem override, usa o peso bruto do seed (job de referência).
    """
    mats = _load("beu_materiais.json")["materiais"]
    ops = _load("beu_operacoes.json")["operacoes"]

    fc = fator_correcao_mo
    if cost_chain is not None and getattr(cost_chain, "fator_correcao_mo", None):
        fc = float(cost_chain.fator_correcao_mo)

    def preco_kgf(material, familia, default):
        """Preço R$/kgf: cadeia de custos do tenant (por material×forma) ou default do seed."""
        if cost_chain is None:
            return default
        fn = getattr(cost_chain, "price_kgf", None)
        if callable(fn):
            try:
                return float(fn(_norm_mat(material), _FAMILIA_FORMA.get(familia, "chapa")))
            except Exception:
                pass
        return default

    # ---- matéria-prima ----
    secoes = {}
    custo_material = 0.0
    for m in mats:
        peso_bruto = m["peso_bruto"]
        # what-if: recomputa peso pela geometria se houver override de dimensões
        if dims_override and m["label"] in dims_override:
            dims = {**m.get("dims", {}), **dims_override[m["label"]]}
            liq = peso_liquido_geom(m["familia"], dims)
            if liq is not None:
                qtd = float(m.get("dims", {}).get("QUANTIDADE", 1) or 1)
                perda = (m["peso_bruto"] / m["peso_liq"]) if m.get("peso_liq") else 1.10
                peso_bruto = liq * qtd * perda
        rate = preco_kgf(m.get("material"), m["familia"], m["price_kgf"])
        custo = peso_bruto * rate
        custo_material += custo
        secoes.setdefault(m["secao"], 0.0)
        secoes[m["secao"]] += custo

    # ---- operações (MO escala com FC) + serviços (fixo) ----
    custo_mo = custo_servico = 0.0
    for o in ops:
        if o["tipo"] == "mao_obra":
            # reconcilia com o gabarito: usa horas×rate×FC + ajuste
            c = o["horas"] * o["rate"] * fc + o.get("ajuste", 0.0)
            custo_mo += c
        else:
            c = o["preco_fixo"]
            custo_servico += c
        secoes.setdefault(o["secao"], 0.0)
        secoes[o["secao"]] += c

    custo_total = custo_material + custo_mo + custo_servico
    # formação de preço ENGEMATEX: custo × F.C. = venda COM impostos;
    # venda SEM impostos = venda_com / gross-up de ICMS (≈1,0965 p/ ICMS 9%)
    preco_com_impostos = custo_total * fator_preco
    gross_up = 1.0 / (1.0 - impostos_pct / 100.0 * 0.97)  # ICMS embutido (calibrado ao gabarito)
    preco_sem_impostos = preco_com_impostos / gross_up

    return {
        "designacao_tema": "BEU",
        "custo_material": round(custo_material, 2),
        "custo_mao_obra": round(custo_mo, 2),
        "custo_servicos": round(custo_servico, 2),
        "custo_total": round(custo_total, 2),
        "por_secao": {k: round(v, 2) for k, v in secoes.items()},
        "fator_correcao_mo": fc,
        "fator_preco": fator_preco,
        "impostos_pct": impostos_pct,
        "preco_com_impostos": round(preco_com_impostos, 2),
        "preco_sem_impostos": round(preco_sem_impostos, 2),
        "n_materiais": len(mats),
        "n_operacoes": len(ops),
    }
