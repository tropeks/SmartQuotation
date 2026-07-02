"""
Entry point do motor: monta a Estrutura Analítica completa de um feixe e forma o preço.

quote_feixe(inputs, cost_chain) → Cotacao (EAP com itens, MP, operações) + preço de venda.

Formação de preço (parametrizável por tenant — vem da cadeia de custos / wizard A1-c):
   custo_total → × fator_preco (markup) → preço_sem_imposto → × (1+impostos%) → preço_com_imposto
"""
from __future__ import annotations
from contextlib import nullcontext
import math
from .feixe_inputs import FeixeInputs
from .operations_registry import REGISTRY
from . import process_params as pp
from .components import componentes_from_inputs, peso_componente, peso_liquido_componente
from .wbs import Cotacao, Item, MateriaPrima, OperacaoExecutada

# códigos de item → descrição (EAP N1)
ITENS = {
    "TUB-01": "Tubos de Troca Térmica", "ESP-01": "Espelhos",
    "CHI-01": "Chicanas", "MON-01": "Montagem do Feixe",
    "UTB-01": "Tubos U", "BAR-01": "Barras",
    "ALC-01": "Alça / Batente", "END-01": "Ensaios / Inspeção / Transporte",
    "ENG-01": "Engenharia", "FER-01": "Ferramentas / Consumíveis",
}

# mapa componente → item da EAP (qual Item N1 carrega cada matéria-prima)
_COMP_ITEM = {
    "TUB-01": "TUB-01", "ESP-2a": "ESP-01", "ESP-2b": "ESP-01",
    "CHI-3": "CHI-01", "SUP-4": "CHI-01", "TIR-7": "MON-01",
    "BSE1-9.1": "BAR-01", "BSE2-9.2": "BAR-01", "BDE-10": "BAR-01",
    "IMP-11": "MON-01", "ESC-6a": "MON-01", "ALC-16": "ALC-01",
    "PLG1-19": "MON-01", "PLG2-20": "MON-01", "OLH1-W1": "ALC-01",
    "OLH2-W2": "ALC-01", "POR-8": "MON-01",
}

_RATE_OVERRIDE = {
    "OP-ESP-TRACAR-FUROS": ("TRACAR_FUROS_ESPELHO", 80),
    "OP-ESP-FURAR": ("FURAR_ESPELHO", 110),
    "OP-ESP-ESCAREAR": ("ESCAREAR_ESPELHO", 110),
    "OP-ESP-ALARGAR": ("ALARGAR_ESPELHO", 110),
    "OP-ESP-GROOVES": ("GROOVES_ESPELHO", 110),
    "OP-ESP-FUROS-TIR": ("USINAR_FUROS_TIRANTES", 110),
    "OP-ESP-TRACAR-RASGOS": ("TRACAR_RASGOS", 80),
    "OP-ESP-ACABAMENTO": ("ACABAMENTO_ESPELHO", 40),
    "OP-CHI-TRACAR-REC": ("CHICANA_TRACAR_RECORTAR", 90),
    "OP-CHI-TRACAR-FUROS": ("TRACAR_FUROS_CHICANA", 80),
    "OP-CHI-FURAR": ("FURAR_CHICANA", 110),
    "OP-CHI-USINAR": ("CHICANA_USINAR", 150),
    "OP-CHI-ESCAREAR": ("ESCAREAR_CHICANA", 110),
    "OP-CHI-RECORTAR-ACAB": ("CHICANA_RECORTAR_ACABAMENTO", 130),
    "OP-PREP-TIRANTES": ("PREPARAR_TIRANTES", 120),
    "OP-INTRODUZIR-TUBOS": ("MONTAR_TUBOS", 40),
    "OP-MON-TUBOS": ("MONTAR_TUBOS", 40),
    "OP-GABARITAR": ("MONTAR_TUBOS", 40),
    "OP-SOLDAR-RAIZ": ("SOLDAR_RAIZ", 90),
    "OP-SOLDAR-ACAB": ("SOLDAR_ACABAMENTO", 90),
    "OP-CURVAR-U": ("CURVAR_TUBO_U", 160),
}


def _apply_rate_override(op, custo: float, cost_chain) -> float:
    if cost_chain is None or not custo:
        return custo
    if op.code == "OP-MANDRILAR":
        return custo
    spec = _RATE_OVERRIDE.get(op.code)
    if not spec:
        return custo
    key, default_rate = spec
    rate = cost_chain.hh(key, default_rate)
    return custo * (rate / default_rate)


def _mandrilar_custo(inp: FeixeInputs, cost_chain) -> float | None:
    if cost_chain is None:
        return None
    hh = math.ceil(pp.get("MANDRILAR", pp.MANUAL) * inp.num_furos / 60 / 2) * inp.fator_correcao_mo
    hm = hh * pp.get("MANDRILAR_HM_FATOR", pp.MANUAL)
    return hh * cost_chain.hh("MANDRILAR", 120) + hm * cost_chain.hm("MANDRILAR", 80)


def quote_feixe(inp: FeixeInputs, cost_chain=None,
                fator_preco: float = 1.01377, impostos_pct: float = 23.303) -> Cotacao:
    """Monta a EAP completa do feixe e forma o preço.

    cost_chain (opcional, rates.TenantCostChain): a CADEIA DE CUSTOS do tenant.
    Quando presente, sobrescreve preços de material (por material×forma) e os fatores
    (correção MO, markup, impostos) — é o que o wizard A1-c popula/calibra. Sem ela,
    usa os defaults ENGEMATEX embutidos (validados a -2,9%).
    """
    import copy as _copy
    if cost_chain is not None:
        # fator de correção de MO (knob de calibração do back-solve) sobrescreve o input
        if getattr(cost_chain, "fator_correcao_mo", None):
            inp = _copy.copy(inp)
            inp.fator_correcao_mo = float(cost_chain.fator_correcao_mo)
        if getattr(cost_chain, "fator_preco", None):
            fator_preco = float(cost_chain.fator_preco)
        if getattr(cost_chain, "impostos_pct", None) is not None:
            impostos_pct = float(cost_chain.impostos_pct)

    def _preco_material(material, forma, default):
        if cost_chain is None:
            return default
        try:
            return float(cost_chain.price_kgf(material, forma))
        except (KeyError, Exception):
            return default

    itens: dict[str, Item] = {code: Item(code, desc) for code, desc in ITENS.items()}

    # --- matérias-primas (peso computado da geometria, paramétrico) ---
    for c in componentes_from_inputs(inp):
        peso, status = peso_componente(c)        # BRUTO (base de custo, Opção A)
        item_code = _COMP_ITEM.get(c.codigo, "MON-01")
        preco = _preco_material(c.material, c.forma, c.rkg)   # tenant price ou default
        mp = MateriaPrima(c.codigo, c.descricao, c.material, c.forma, peso, preco)
        mp.peso_liquido = peso_liquido_componente(c)   # informativo (refugo = bruto - líquido)
        itens[item_code].materias_primas.append(mp)

    override_ctx = (
        pp.override(getattr(cost_chain, "process_params", None))
        if cost_chain is not None else nullcontext()
    )
    with override_ctx:
        # --- operações (custo computado das fórmulas) ---
        for op in REGISTRY:
            try:
                aplic = op.applicable(inp)
                if aplic and op.code == "OP-MANDRILAR":
                    custo = _mandrilar_custo(inp, cost_chain)
                    if custo is None:
                        custo = op.compute(inp)
                else:
                    custo = op.compute(inp) if aplic else 0.0
                custo = _apply_rate_override(op, custo, cost_chain)
            except Exception as exc:
                raise RuntimeError(f"Erro calculando operação {op.code} ({op.label})") from exc
            it = itens.get(op.item, itens["MON-01"])
            oe = OperacaoExecutada(op.code, op.label, aplicavel=aplic, custo_fixo=custo)
            if op.group in ("ensaios",):
                it.ensaios.append(oe)
            else:
                it.operacoes.append(oe)

    # engenharia e ferramentas entram como custos separados na Cotacao
    custo_eng = sum(o.custo for o in itens["ENG-01"].operacoes + itens["ENG-01"].ensaios)
    custo_fer = sum(o.custo for o in itens["FER-01"].operacoes)

    cot = Cotacao(
        codigo="COT-FEIXE-136", descricao="Feixe Tubular 136 tubos (SA-179) — Petrobras RPBC",
        itens=[it for code, it in itens.items() if code not in ("ENG-01", "FER-01")],
        custo_engenharia=custo_eng, custo_ferramentas=custo_fer,
        fator_preco=fator_preco, impostos_pct=impostos_pct,
    )
    return cot
