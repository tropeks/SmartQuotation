"""
Serviços do wizard de cadeia de custos (A1-c).

- build_chain_from_db(fator_mo): monta TenantCostChain com os preços de material do banco.
- back_solve(reference_inputs, known_price): acha o fator de correção de MO que faz o motor
  reproduzir o preço REAL conhecido (bisseção — preço é monotônico no fator). É a calibração.
- apply_top_down(...): grava preços de material + fatores (seed dos custos de cabeça).
"""
from dataclasses import fields
from datetime import date
from decimal import Decimal
from django.db import models

from pricing_engine.feixe_inputs import FeixeInputs, caso_136_tubos
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import TenantCostChain, op_key

DEFAULT_FATOR_PRECO = 1.01377
DEFAULT_IMPOSTOS = 23.303
_FIELD_NAMES = {f.name for f in fields(FeixeInputs)}


def _inputs(d: dict) -> FeixeInputs:
    base = {f.name: getattr(caso_136_tubos(), f.name) for f in fields(FeixeInputs)}
    base.update({k: v for k, v in (d or {}).items() if k in _FIELD_NAMES})
    return FeixeInputs(**base)


def build_chain_from_db(fator_mo: float = 1.0,
                        fator_preco: float = DEFAULT_FATOR_PRECO,
                        impostos_pct: float = DEFAULT_IMPOSTOS) -> TenantCostChain:
    chain = TenantCostChain(fator_correcao_mo=fator_mo, fator_preco=fator_preco, impostos_pct=impostos_pct)
    try:
        from apps.materials.models import MaterialPrice
        # Resolução única em MaterialPriceManager: antes, iterar sem order_by deixava
        # o último registro do queryset vencer — com duas vigências válidas no mesmo
        # dia, o preço que entrava no orçamento era o que o banco devolvesse por último.
        chain.material_price.update(
            {chave: float(valor) for chave, valor in MaterialPrice.objects.mapa_vigente().items()})
    except Exception:
        pass
    try:
        from apps.engineering_params.models import Rate
        hoje = date.today()
        for r in (Rate.objects.filter(valid_from__lte=hoje)
                  .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=hoje))
                  .order_by("valid_from")):
            chain.rate_hh[op_key(r.operacao)] = float(r.rate_hh)
            if r.rate_hm is not None:
                chain.rate_hm[op_key(r.operacao)] = float(r.rate_hm)
    except Exception:
        pass
    return chain


def _price_at(inputs: FeixeInputs, fator_mo: float, fator_preco: float, impostos_pct: float) -> float:
    chain = build_chain_from_db(fator_mo, fator_preco, impostos_pct)
    return float(quote_feixe(inputs, cost_chain=chain).preco_com_impostos)


def back_solve(reference_inputs: dict, known_price: float,
               fator_preco: float = DEFAULT_FATOR_PRECO, impostos_pct: float = DEFAULT_IMPOSTOS,
               lo: float = 0.05, hi: float = 10.0, tol: float = 0.0005, iters: int = 60) -> dict:
    """Acha o fator de correção de MO que reproduz o preço conhecido (bisseção).
    Retorna {fator, achieved, error_pct}."""
    inputs = _inputs(reference_inputs)
    known = float(known_price)
    p_lo = _price_at(inputs, lo, fator_preco, impostos_pct)
    p_hi = _price_at(inputs, hi, fator_preco, impostos_pct)
    if known <= p_lo:                      # preço alvo abaixo do mínimo: usa lo
        return {"fator": lo, "achieved": p_lo, "error_pct": (p_lo - known) / known * 100}
    if known >= p_hi:
        return {"fator": hi, "achieved": p_hi, "error_pct": (p_hi - known) / known * 100}
    mid = (lo + hi) / 2
    for _ in range(iters):
        mid = (lo + hi) / 2
        price = _price_at(inputs, mid, fator_preco, impostos_pct)
        if abs(price - known) / known <= tol:
            break
        if price < known:
            lo = mid
        else:
            hi = mid
    price = _price_at(inputs, mid, fator_preco, impostos_pct)
    return {"fator": round(mid, 4), "achieved": round(price, 2),
            "error_pct": round((price - known) / known * 100, 3)}


def run_back_solve(session) -> "object":
    """Roda o back-solve da sessão, grava o fator e APLICA no TenantParamConfig."""
    r = back_solve(session.reference_inputs, float(session.reference_known_price))
    session.solved_fator_mo = Decimal(str(r["fator"]))
    session.achieved_price = Decimal(str(r["achieved"]))
    session.error_pct = Decimal(str(r["error_pct"]))
    session.save()
    _apply_fator_mo(r["fator"])
    return session


def _apply_fator_mo(fator: float) -> None:
    from apps.engineering_params.models import TenantParamConfig
    cfg = TenantParamConfig.get_solo()
    cfg.fator_correcao_mo = Decimal(str(round(fator, 4)))
    cfg.save()


def apply_top_down(prices: list, fator_mo: float = None) -> dict:
    """Seed top-down: grava preços de material (sigla, forma, preço) e o fator de MO.
    prices: lista de dicts {sigla, forma, preco}."""
    from apps.materials.models import Material, MaterialPrice
    hoje = date.today()
    gravados = 0
    for p in prices:
        mat = Material.objects.filter(sigla__iexact=p["sigla"]).first()
        if not mat:
            continue
        MaterialPrice.objects.create(material=mat, forma=p["forma"],
                                     preco_brl_kg=str(p["preco"]), valid_from=hoje)
        gravados += 1
    if fator_mo is not None:
        _apply_fator_mo(float(fator_mo))
    return {"precos_gravados": gravados, "fator_mo": fator_mo}
