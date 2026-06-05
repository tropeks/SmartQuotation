"""
Motor de custeio GENÉRICO de permutador casco-tubo completo (qualquer designação TEMA
cujo gabarito foi extraído: BEU, BEM, ...).

quote_completo(designacao, cost_chain) compõe a Estrutura Analítica:
  matéria-prima  = Σ peso_bruto(geometria) × preço/kgf   (itens de catálogo: preço fixo)
  mão-de-obra    = Σ (preço_base) × FC + ajuste            (FC = fator de correção de MO)
  serviços       = Σ preço_fixo                            (terceiros / ensaios / insumos)

A cadeia de custos do tenant (rates.TenantCostChain) sobrescreve o fator de MO e os preços
de material por (material × forma) — mesmo contrato do feixe. Sem ela, usa os defaults
ENGEMATEX embutidos nos seeds (validados ao gabarito real de cada designação).

Seeds por designação: pricing_engine/seeds/{designacao}_materiais.json + _operacoes.json.
"""
from __future__ import annotations
import json
import os

from .beu_geometry import peso_liquido_geom, RHO

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")


def _rho(material):
    """Densidade kgf/mm³ do material (de norma, via materials.density), default aço-carbono."""
    try:
        from .materials import density
        return density(material or "")
    except Exception:
        return RHO


def gross_up_icms(impostos_pct: float) -> float:
    """Gross-up de imposto sobre o preço de venda.

    LIMITAÇÃO/ACHADO #4: o ICMS brasileiro é 'por dentro' (fórmula legal 1/(1−alíquota)).
    O fator 0,97 aqui é uma CALIBRAÇÃO empírica que aproxima a razão venda_com/venda_sem do
    gabarito ENGEMATEX (que embute outros efeitos — PIS/COFINS, base reduzida). NÃO é uma
    fórmula fiscal pura; deve ser substituído por um motor fiscal real (regime + alíquotas
    por tributo) quando formos modelar imposto a sério.
    """
    return 1.0 / (1.0 - impostos_pct / 100.0 * 0.97)

# família geométrica → forma de matéria-prima (chave da TenantCostChain.material_price)
_FAMILIA_FORMA = {
    "tubo": "tubo", "pipe": "tubo", "chapa_retangular": "chapa",
    "disco": "chapa", "tampo_2_1": "chapa", "anel": "forjado", "flange_wn": "forjado",
}


def _load(nome):
    with open(os.path.join(_SEEDS, nome), encoding="utf-8") as f:
        return json.load(f)


def _norm_mat(material):
    return (material or "").strip().upper()


def designacoes_disponiveis():
    """Designações com seeds de custeio presentes (ex.: ['BEM', 'BEU'])."""
    achadas = set()
    for fn in os.listdir(_SEEDS):
        if fn.endswith("_materiais.json"):
            achadas.add(fn[:-len("_materiais.json")].upper())
    return sorted(achadas)


def quote_completo(designacao: str = "BEU", cost_chain=None, fator_correcao_mo: float = 1.0,
                   fator_preco: float = 1.25, impostos_pct: float = 9.0,
                   dims_override: dict | None = None,
                   scale_factors: dict | None = None) -> dict:
    """scale_factors: {grupo: fator} p/ escalar as HORAS de fabricação pelo driver físico
    (feixe=nº tubos, chicanas=nº chicanas, casco=comprimento). Calibrado do job de
    referência (fator 1,0 = caso de referência → reconcilia 0,0%). Grupo 'fixo' (config:
    nº de bocais/flanges) e serviços de terceiros NÃO escalam — limitação conhecida."""
    sf = scale_factors or {}
    d = designacao.lower()
    mats = _load(f"{d}_materiais.json")["materiais"]
    ops = _load(f"{d}_operacoes.json")["operacoes"]

    fc = fator_correcao_mo
    if cost_chain is not None and getattr(cost_chain, "fator_correcao_mo", None):
        fc = float(cost_chain.fator_correcao_mo)

    def preco_kgf(material, familia, default):
        if cost_chain is None:
            return default
        fn = getattr(cost_chain, "price_kgf", None)
        if callable(fn):
            try:
                return float(fn(_norm_mat(material), _FAMILIA_FORMA.get(familia, "chapa")))
            except Exception:
                pass
        return default

    secoes = {}
    custo_material = 0.0
    for m in mats:
        if m.get("familia") == "catalogo" or not m.get("peso_bruto"):
            custo = m["preco"]                       # item de catálogo (preço fixo)
        else:
            peso_bruto = m["peso_bruto"]
            if dims_override and m["label"] in dims_override:
                dims = {**m.get("dims", {}), **dims_override[m["label"]]}
                liq = peso_liquido_geom(m["familia"], dims, rho=_rho(m.get("material")))
                if liq is not None:
                    qtd = float(m.get("dims", {}).get("QUANTIDADE", 1) or 1)
                    perda = (m["peso_bruto"] / m["peso_liq"]) if m.get("peso_liq") else 1.10
                    peso_bruto = liq * qtd * perda
            custo = peso_bruto * preco_kgf(m.get("material"), m["familia"], m["price_kgf"])
        custo_material += custo
        secoes[m["secao"]] = secoes.get(m["secao"], 0.0) + custo

    custo_mo = custo_servico = 0.0
    mo_por_grupo = {}
    for o in ops:
        if o["tipo"] == "mao_obra":
            ajuste = o.get("ajuste", 0.0)
            grupo = o.get("grupo", "fixo")
            fator = float(sf.get(grupo, 1.0))         # escala de horas pelo driver físico
            base = o["preco_gabarito"] - ajuste       # parcela de MO (R$ a FC=1, ref)
            c = base * fator * fc + ajuste
            custo_mo += c
            mo_por_grupo[grupo] = round(mo_por_grupo.get(grupo, 0.0) + c, 2)
        else:
            c = o["preco_gabarito"]                    # serviço/terceiro: fixo (não escala)
            custo_servico += c
        secoes[o["secao"]] = secoes.get(o["secao"], 0.0) + c

    custo_total = custo_material + custo_mo + custo_servico
    # formação de preço ENGEMATEX: custo × F.C. = venda COM impostos; venda SEM impostos
    # por dedução do gross-up de imposto (ver gross_up_icms — calibração, não fórmula fiscal).
    preco_com_impostos = custo_total * fator_preco
    preco_sem_impostos = preco_com_impostos / gross_up_icms(impostos_pct)

    return {
        "designacao_tema": designacao.upper(),
        "custo_material": round(custo_material, 2),
        "custo_mao_obra": round(custo_mo, 2),
        "custo_mo_por_grupo": mo_por_grupo,
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
