"""
Entry point do motor: monta a Estrutura Analítica completa de um feixe e forma o preço.

quote_feixe(inputs, cost_chain) → Cotacao (EAP com itens, MP, operações) + preço de venda.

Formação de preço (parametrizável por tenant — vem da cadeia de custos / wizard A1-c):
   custo_total → × fator_preco (markup) → preço_sem_imposto → × (1+impostos%) → preço_com_imposto
"""
from __future__ import annotations
from .feixe_inputs import FeixeInputs
from .operations_registry import REGISTRY
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

    # --- operações (custo computado das fórmulas) ---
    for op in REGISTRY:
        try:
            aplic = op.applicable(inp)
            custo = op.compute(inp) if aplic else 0.0
        except Exception:
            aplic, custo = False, 0.0
        it = itens.get(op.item, itens["MON-01"])
        oe = OperacaoExecutada(op.code, op.label, aplicavel=aplic, custo_fixo=custo)
        if op.group in ("engenharia",):
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
