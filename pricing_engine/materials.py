"""
Catálogo de materiais (densidade) — seed da planilha ENGEMATEX (aba P.E., 423 materiais).

`densidade_kg_mm3` é dado de NORMA (constante física), não de tenant.
`MaterialPrice` (R$/kgf) é dado de TENANT, editável, por (material × forma) — ver rates.py.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass

_SEEDS = os.path.join(os.path.dirname(__file__), "seeds")


@dataclass(frozen=True)
class Material:
    sigla: str
    tipo: str
    densidade_kg_mm3: float | None
    norma: str = ""
    forma_padrao: str = ""


def _norm(s: str) -> str:
    return str(s).strip().upper().replace("SA-", "A-").replace("SA ", "A-")


def load_materials() -> dict[str, Material]:
    """Carrega o catálogo; chaveado por sigla normalizada. Limpa densidades inválidas."""
    with open(os.path.join(_SEEDS, "materials_pe.json"), encoding="utf-8") as fp:
        raw = json.load(fp)
    cat: dict[str, Material] = {}
    for m in raw:
        pe = m.get("pe_kg_mm3")
        dens = pe if isinstance(pe, (int, float)) else None  # descarta "CROMOL"/vazio
        sigla = str(m.get("sigla", "")).strip()
        if not sigla:
            continue
        cat[_norm(sigla)] = Material(
            sigla=sigla, tipo=str(m.get("tipo", "")).strip(),
            densidade_kg_mm3=dens, norma=str(m.get("norma", "")).strip(),
            forma_padrao=str(m.get("prod", "")).strip(),
        )
    return cat


_CATALOG: dict[str, Material] | None = None

# fallbacks de densidade por grupo, p/ materiais com PE corrompido na origem (kg/mm³)
_DENSITY_FALLBACK = {
    "AÇO CARBONO": 7.85e-6, "AÇO INOX SS-300": 8.007e-6, "AÇO INOX SS-400": 7.75e-6,
    "SUPER DUPLEX": 7.805e-6, "DUPLEX": 7.805e-6,
}

# fallback direto por sigla p/ materiais comuns fora do catálogo P.E. (kg/mm³)
_DENSITY_BY_SIGLA = {
    "AISI-304": 8.0e-6, "AISI-316": 8.0e-6, "SAE-1045": 7.85e-6, "SAE-1020": 7.85e-6,
    "SA-194 GR 2H": 7.85e-6, "SA-214": 7.85e-6, "SA-36": 7.85e-6,
}


def density(sigla: str, tipo_hint: str = "") -> float:
    """Densidade kg/mm³ de um material (sigla). Usa fallback por grupo se a origem falhar."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_materials()
    m = _CATALOG.get(_norm(sigla))
    if m and m.densidade_kg_mm3:
        return m.densidade_kg_mm3
    grupo = (m.tipo if m else "") or tipo_hint
    if grupo in _DENSITY_FALLBACK:
        return _DENSITY_FALLBACK[grupo]
    s = str(sigla).strip().upper()
    if s in _DENSITY_BY_SIGLA:
        return _DENSITY_BY_SIGLA[s]
    raise KeyError(f"Densidade indisponível p/ material {sigla!r} (grupo {grupo!r})")
