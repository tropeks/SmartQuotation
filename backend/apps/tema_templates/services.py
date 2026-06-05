"""Ponte composição TEMA ↔ motor de custeio do permutador completo (pricing_engine.beu_quote).

Designações TEMA com custeio paramétrico validado contra gabarito ENGEMATEX.
Hoje: BEU (bonnet + casco 1 passe + feixe em U), Δ -0,3% vs R$ 128.160.
Casco/cabeçote de outras letras reaproveitam os mesmos blocos à medida que forem validados.
"""
from __future__ import annotations

# designações cujo custeio paramétrico já foi validado contra gabarito real
COSTABLE = {"BEU"}


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
    if (designacao or "").upper() not in COSTABLE:
        return None
    from pricing_engine.beu_quote import quote_beu
    return quote_beu(cost_chain=tenant_cost_chain())
