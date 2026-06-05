"""
Compat: quote_beu(...) = quote_completo("BEU", ...).

O motor de custeio do permutador completo passou a ser GENÉRICO por designação TEMA —
ver pricing_engine/permutador_quote.py (BEU, BEM, ...). Este módulo mantém a API antiga.
"""
from __future__ import annotations

from .permutador_quote import quote_completo


def quote_beu(cost_chain=None, fator_correcao_mo: float = 1.0,
              fator_preco: float = 1.25, impostos_pct: float = 9.0,
              dims_override: dict | None = None) -> dict:
    return quote_completo("BEU", cost_chain=cost_chain, fator_correcao_mo=fator_correcao_mo,
                          fator_preco=fator_preco, impostos_pct=impostos_pct,
                          dims_override=dims_override)
