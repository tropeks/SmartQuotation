"""
Peso de flanges (Welding Neck, Slip-On e Blind) por Ø × classe de pressão — tabela ENGEMATEX
(ASME B16.5 / B16.47), puxar o peso real em vez de chutar.

peso_flange(rating, nps, sched, tipo) → kgf/peça (aço-carbono). Seeds: flanges_wn.json, flanges_so_bl.json.
O peso real corrige o peso final do equipamento e alimenta as horas de solda dos bocais.
"""
from __future__ import annotations
import json
import os

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")
_TABELA_WN = None
_TABELA_SO_BL = None

def _load_wn():
    global _TABELA_WN
    if _TABELA_WN is None:
        with open(os.path.join(_SEEDS, "flanges_wn.json"), encoding="utf-8") as f:
            _TABELA_WN = json.load(f)["tabela"]
    return _TABELA_WN

def _load_so_bl():
    global _TABELA_SO_BL
    if _TABELA_SO_BL is None:
        with open(os.path.join(_SEEDS, "flanges_so_bl.json"), encoding="utf-8") as f:
            _TABELA_SO_BL = json.load(f)["tabela"]
    return _TABELA_SO_BL


def _norm_nps(nps):
    s = str(nps).strip()
    return s if s.endswith('"') else s + '"'


def _norm_classe(rating):
    s = str(rating).strip().upper()
    return s if s.endswith("#") else s + "#"


def _norm_sched(sched):
    s = str(sched).strip().upper().replace(".0", "")
    return s.replace("SCH.", "").replace("SCH", "").strip()   # aceita 'SCH 80', 'SCH. 80'


def peso_flange(rating, nps, sched=None, tipo="WN") -> float | None:
    """Peso (kgf/peça) do flange. Suporta tipos 'WN', 'SO' e 'BL'."""
    tipo = str(tipo).strip().upper()
    nps_norm = _norm_nps(nps)
    rating_norm = _norm_classe(rating)

    if tipo in ("SO", "BL"):
        tab_tipo = _load_so_bl().get(tipo, {})
        tab_rating = tab_tipo.get(rating_norm, {})
        return tab_rating.get(nps_norm)

    # Lógica original WN
    tab = _load_wn().get(rating_norm, {}).get(nps_norm)
    if not tab:
        return None
    if sched is not None and _norm_sched(sched) in tab:
        return tab[_norm_sched(sched)]
    for fallback in ("STD", "40", "XS", "80"):     # schedules usuais como fallback
        if fallback in tab:
            return tab[fallback]
    # último recurso: o MAIOR peso disponível (conservador — nunca subestimar a peça)
    return max(tab.values()) if tab else None


def peso_flange_dims(dims) -> float | None:
    """Peso total (kgf) a partir das dimensões do material no seed (ND/RATING/SCH/QUANTIDADE)."""
    nps = dims.get("ND") or dims.get("DIÂMETRO")
    rating = dims.get("RATING")
    tipo = dims.get("TIPO", "WN")
    if not (nps and rating):
        return None
    p = peso_flange(rating, nps, dims.get("SCH"), tipo=tipo)
    if p is None:
        return None
    qtd = float(dims.get("QUANTIDADE", 1) or 1)
    return p * qtd
