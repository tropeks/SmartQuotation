"""
Entry point do motor: monta a Estrutura Analítica completa de um feixe e forma o preço.

quote_feixe(inputs, cost_chain) → Cotacao (EAP com itens, MP, operações) + preço de venda.

Formação de preço (parametrizável por tenant — vem da cadeia de custos / wizard A1-c):
   custo_total → × fator_preco (markup) → preço_sem_imposto → × (1+impostos%) → preço_com_imposto
"""
from __future__ import annotations
from .feixe_inputs import FeixeInputs
from .operations_registry import REGISTRY
from .components import feixe_136_componentes, peso_componente
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
    """Monta a EAP completa do feixe e forma o preço."""
    itens: dict[str, Item] = {code: Item(code, desc) for code, desc in ITENS.items()}

    # --- matérias-primas (peso computado da geometria) ---
    for c in feixe_136_componentes():
        peso, status = peso_componente(c)
        item_code = _COMP_ITEM.get(c.codigo, "MON-01")
        itens[item_code].materias_primas.append(
            MateriaPrima(c.codigo, c.descricao, c.material, c.forma, peso, c.rkg))

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
