"""
Simulação de impacto (EPICO 4) — recota um golden case do tenant com um valor
PROPOSTO de Rate/ProcessParameter sobreposto em memória e compara vs o custo atual.

NADA é persistido: a cadeia de custos é uma cópia (deepcopy) da cadeia vigente do
tenant com o valor editado sobreposto; pricing_engine.quote_feixe roda puro sobre
ela. Não usa apps.quotations.adapter.recompute (que grava a EAP no banco).
"""
from copy import deepcopy
from decimal import Decimal

from apps.quotations.adapter import build_cost_chain
from apps.quotations.models import Quotation
from pricing_engine.feixe_inputs import caso_of_3672
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import op_key


def _golden_case_inputs():
    """OF-3672 (REPLAN) — golden case real do PE Wellington, roteado pelo motor feixe."""
    return caso_of_3672()


def _tenant_chain():
    """Cadeia de custos vigente do tenant, com os fatores default do golden case
    (build_cost_chain só lê fator_preco/impostos_pct do objeto — não precisa persistir)."""
    return build_cost_chain(Quotation())


def _diff(baseline, proposto):
    delta = Decimal(str(proposto.custo_total)) - Decimal(str(baseline.custo_total))
    delta_pct = (
        (delta / Decimal(str(baseline.custo_total)) * 100)
        if baseline.custo_total
        else Decimal("0")
    )
    return {
        "custo_total_atual": Decimal(str(baseline.custo_total)),
        "custo_total_proposto": Decimal(str(proposto.custo_total)),
        "delta_custo": delta,
        "delta_pct": delta_pct,
        "preco_atual": Decimal(str(baseline.preco_com_impostos)),
        "preco_proposto": Decimal(str(proposto.preco_com_impostos)),
        "delta_preco": Decimal(str(proposto.preco_com_impostos)) - Decimal(str(baseline.preco_com_impostos)),
    }


def simulate_rate_change(operacao, rate_hh=None, rate_hm=None):
    """Simula alterar rate_hh/rate_hm de `operacao` no golden case. Retorna dict de deltas."""
    inputs = _golden_case_inputs()
    chain = _tenant_chain()
    baseline = quote_feixe(inputs, cost_chain=chain)

    proposed_chain = deepcopy(chain)
    key = op_key(operacao)
    if rate_hh is not None:
        proposed_chain.rate_hh[key] = float(rate_hh)
    if rate_hm is not None:
        proposed_chain.rate_hm[key] = float(rate_hm)

    proposto = quote_feixe(inputs, cost_chain=proposed_chain)
    return _diff(baseline, proposto)


def simulate_process_parameter_change(operacao, metodo, material, valor):
    """Simula alterar o valor de um ProcessParameter (operacao × metodo × material) no
    golden case. Retorna dict de deltas."""
    inputs = _golden_case_inputs()
    chain = _tenant_chain()
    baseline = quote_feixe(inputs, cost_chain=chain)

    proposed_chain = deepcopy(chain)
    proposed_chain.process_params[(operacao, metodo, material or None)] = float(valor)

    proposto = quote_feixe(inputs, cost_chain=proposed_chain)
    return _diff(baseline, proposto)
