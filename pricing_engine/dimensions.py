"""
Padrões dimensionais e cálculo de geometria → peso.

Fonte: tabelas OD / BWG da planilha ENGEMATEX (Layer 1 — padrões ANSI/ASME).
Estes valores são CONSTANTES de norma, não parâmetros de tenant.

        OD (mm)                wall (mm)
   3/4" ───┐               BWG14 ───┐
           ▼                        ▼
   ┌─────────────┐
   │ ┌─────────┐ │   área da seção = π/4 (OD² − ID²)
   │ │   ID    │ │   ID = OD − 2·wall
   │ └─────────┘ │   peso = área · comprimento · densidade
   └─────────────┘
"""
from __future__ import annotations
import json
import math
import os

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")


def _load(name: str) -> dict:
    with open(os.path.join(_SEEDS, name), encoding="utf-8") as fp:
        return json.load(fp)


_DIM = _load("dim_standards.json")
TUBE_OD_INCH_TO_MM: dict[str, float] = _DIM["tube_od_inch_to_mm"]
BWG_TO_MM: dict[str, float] = _DIM["bwg_to_mm"]


def tube_od_mm(od_spec: str) -> float:
    """Converte spec de OD ('3/4"') para mm. Aceita já-em-mm (float-like)."""
    s = str(od_spec).strip()
    if s in TUBE_OD_INCH_TO_MM:
        return TUBE_OD_INCH_TO_MM[s]
    try:
        return float(s)
    except ValueError:
        raise KeyError(f"OD desconhecido: {od_spec!r}")


def tube_wall_mm(wall_spec: str) -> float:
    """Converte spec de parede ('BWG 14') para mm. Aceita já-em-mm."""
    s = str(wall_spec).strip()
    if s in BWG_TO_MM:
        return BWG_TO_MM[s]
    s2 = s.upper().replace("BWG", "").strip()
    if f"BWG {s2}" in BWG_TO_MM:
        return BWG_TO_MM[f"BWG {s2}"]
    try:
        return float(s)
    except ValueError:
        raise KeyError(f"Parede desconhecida: {wall_spec!r}")


def tube_section_area_mm2(od_mm: float, wall_mm: float) -> float:
    """Área da seção transversal (anel) do tubo, em mm²."""
    id_mm = od_mm - 2 * wall_mm
    if id_mm <= 0:
        raise ValueError(f"ID não-positivo: OD={od_mm} wall={wall_mm}")
    return math.pi / 4 * (od_mm ** 2 - id_mm ** 2)


def tube_weight_kg(od_spec: str, wall_spec: str, length_mm: float,
                   qty: int, density_kg_mm3: float) -> float:
    """Peso total de um conjunto de tubos (kg)."""
    od = tube_od_mm(od_spec)
    wall = tube_wall_mm(wall_spec)
    area = tube_section_area_mm2(od, wall)
    return area * length_mm * density_kg_mm3 * qty


def disc_weight_kg(od_mm: float, thickness_mm: float,
                   density_kg_mm3: float, qty: int = 1) -> float:
    """Peso de disco/chapa circular cheia (espelho) — kg. (sem desconto de furos)"""
    area = math.pi / 4 * od_mm ** 2
    return area * thickness_mm * density_kg_mm3 * qty
