"""
Peso de flange Welding Neck (WN) por Ø × classe de pressão × schedule — tabela ENGEMATEX
(ASME B16.5 / B16.47), resposta do Wellington (A3): puxar o peso real em vez de chutar.

peso_flange(rating, nps, sched) → kgf/peça (aço-carbono). Seed: seeds/flanges_wn.json.
O peso real corrige o peso final do equipamento e alimenta as horas de solda dos bocais.
"""
from __future__ import annotations
import json
import os

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")
_TABELA = None


def _load():
    global _TABELA
    if _TABELA is None:
        with open(os.path.join(_SEEDS, "flanges_wn.json"), encoding="utf-8") as f:
            _TABELA = json.load(f)["tabela"]
    return _TABELA


def _norm_nps(nps):
    s = str(nps).strip()
    return s if s.endswith('"') else s + '"'


def _norm_classe(rating):
    s = str(rating).strip().upper()
    return s if s.endswith("#") else s + "#"


def _norm_sched(sched):
    s = str(sched).strip().upper().replace(".0", "")
    return s.replace("SCH.", "").replace("SCH", "").strip()   # aceita 'SCH 80', 'SCH. 80'


def peso_flange(rating, nps, sched=None) -> float | None:
    """Peso (kgf/peça) do flange WN. Sem schedule (ou ausente na tabela) usa 'STD'/o mais leve."""
    tab = _load().get(_norm_classe(rating), {}).get(_norm_nps(nps))
    if not tab:
        return None
    if sched is not None and _norm_sched(sched) in tab:
        return tab[_norm_sched(sched)]
    for fallback in ("STD", "40", "XS", "80"):     # schedules usuais como fallback
        if fallback in tab:
            return tab[fallback]
    # último recurso: o MAIOR peso disponível (conservador — nunca subestimar a peça) — #agy
    return max(tab.values()) if tab else None


def peso_flange_dims(dims) -> float | None:
    """Peso total (kgf) a partir das dimensões do material no seed (ND/RATING/SCH/QUANTIDADE)."""
    nps = dims.get("ND") or dims.get("DIÂMETRO")
    rating = dims.get("RATING")
    if not (nps and rating):
        return None
    p = peso_flange(rating, nps, dims.get("SCH"))
    if p is None:
        return None
    qtd = float(dims.get("QUANTIDADE", 1) or 1)
    return p * qtd
