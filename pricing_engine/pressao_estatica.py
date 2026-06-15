"""
Pressão estática de coluna de fluido (ASME VIII Div.1 UG-21): a pressão de projeto no ponto
mais baixo do componente deve incluir a carga hidrostática da coluna de líquido (ρ·g·h).
Pequena para a maioria dos trocadores, mas a norma exige incluí-la.
"""
from __future__ import annotations

G = 9.80665   # m/s² (gravidade padrão)


def pressao_estatica_bar(densidade_kg_m3: float, altura_m: float) -> float:
    """Pressão da coluna estática em bar = ρ·g·h / 1e5 (ρ em kg/m³, h em m)."""
    return densidade_kg_m3 * G * altura_m / 1.0e5


def pressao_total_bar(pressao_projeto_bar: float, densidade_kg_m3: float,
                      altura_m: float) -> float:
    """Pressão de projeto total (UG-21) = pressão de projeto + coluna estática do fluido."""
    return pressao_projeto_bar + pressao_estatica_bar(densidade_kg_m3 or 0, altura_m or 0)
