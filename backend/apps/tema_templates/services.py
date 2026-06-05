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


def reference_inputs(designacao: str):
    """Valores de referência (do seed) p/ pré-preencher o data sheet do trocador completo."""
    d = (designacao or "").upper()
    if d not in COSTABLE:
        return {}
    import json
    import os
    from pricing_engine import permutador_quote as pq
    path = os.path.join(os.path.dirname(pq.__file__), "seeds", f"{d.lower()}_materiais.json")
    try:
        mats = json.load(open(path, encoding="utf-8"))["materiais"]
    except Exception:
        return {}
    by_label = {m["label"]: m.get("dims", {}) for m in mats if m.get("label")}
    tub = by_label.get("TUBOS DE TROCA TÉRMICA", {})
    vir = by_label.get("VIROLA", {})
    return {
        "designacao": d,
        "n_tubos": tub.get("QUANTIDADE"),
        "comprimento_tubo_mm": tub.get("COMPR."),
        "od_tubo_mm": tub.get("OD"),
        "esp_tubo_mm": tub.get("ESP."),
        "comprimento_casco_mm": vir.get("COMPR."),
        "fator_correcao_mo": 1.0,
    }


def estimate_complete(designacao: str, dims_override: dict | None = None,
                      fator_correcao_mo: float | None = None):
    """Estimativa de custo/preço de um permutador completo pela designação TEMA.

    dims_override: {label_material: {dim: valor}} — dimensões reais do projeto que
    recomputam o peso geométrico (parametria de verdade, não replay do seed). Ex.:
    {"TUBOS DE TROCA TÉRMICA": {"COMPR.": 8000, "QUANTIDADE": 200}}.
    fator_correcao_mo: sobrescreve o fator de MO (default = o do TenantParamConfig).

    Retorna dict do motor (custo por seção + preço) ou None se não é custeável.
    """
    d = (designacao or "").upper()
    if d not in COSTABLE:
        return None
    from pricing_engine.permutador_quote import quote_completo
    chain = tenant_cost_chain()
    if fator_correcao_mo is not None:
        chain.fator_correcao_mo = float(fator_correcao_mo)
    return quote_completo(d, cost_chain=chain, dims_override=dims_override or None)
