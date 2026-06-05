"""Ponte composição TEMA ↔ motor de custeio do permutador completo (pricing_engine).

Designações TEMA com custeio paramétrico validado contra gabarito ENGEMATEX:
  BEU (bonnet + casco 1 passe + feixe em U)        — Δ 0,0% vs R$ 128.160
  BEM (bonnet + casco 1 passe + cabeçote fixo)     — Δ 0,0% vs R$ 119.295
Derivado dinamicamente dos seeds presentes (pricing_engine/seeds/{d}_materiais.json).
"""
from __future__ import annotations

from pricing_engine.permutador_quote import designacoes_disponiveis

# designações cujo custeio paramétrico já foi validado contra gabarito real
COSTABLE = set(designacoes_disponiveis())


def tenant_cost_chain():
    """Monta a TenantCostChain do tenant (preços de material cifrados + fator de MO),
    reaproveitando o mesmo padrão do adapter de cotações. Sem dados → None (usa defaults)."""
    from pricing_engine.rates import TenantCostChain
    chain = TenantCostChain()
    try:
        from datetime import date
        from apps.materials.models import MaterialPrice
        hoje = date.today()
        for mp in MaterialPrice.objects.select_related("material").filter(valid_from__lte=hoje):
            if mp.valid_until and mp.valid_until < hoje:
                continue
            try:
                chain.material_price[(mp.material.sigla.upper(), mp.forma.lower())] = float(mp.preco_brl_kg)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    try:
        from apps.engineering_params.models import TenantParamConfig
        chain.fator_correcao_mo = float(TenantParamConfig.get_solo().fator_correcao_mo)
    except Exception:
        pass
    return chain


def estimate_complete(designacao: str):
    """Estimativa de custo/preço de um permutador completo pela designação TEMA.
    Retorna dict do motor (custo por seção + preço) ou None se a designação não é custeável."""
    d = (designacao or "").upper()
    if d not in COSTABLE:
        return None
    from pricing_engine.permutador_quote import quote_completo
    return quote_completo(d, cost_chain=tenant_cost_chain())
