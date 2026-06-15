"""
Estimativa do nº de exposições radiográficas (chapas de filme) de um equipamento, base física
do custo de RT segundo ASME Seção V, Artigo 2 (T-271 técnica + cobertura). O custo de RT escala
com o número de exposições, não com a metragem linear pura.

LIMITAÇÃO (declarada na UI): comprimento útil de filme e sobreposição são DEFAULTS de chão de
fábrica (a confirmar com a engenharia), como os valores de S antes da edição licenciada. A
contagem (ceil por cobertura) é exata para os parâmetros dados.
"""
from __future__ import annotations

import math

# comprimento útil de filme por exposição (mm): filme ~350mm menos ~10% de sobreposição. DEFAULT.
FILME_UTIL_MM = 315.0


def n_exposicoes(comprimento_junta_mm: float, filme_util_mm: float = FILME_UTIL_MM) -> int:
    """Nº de exposições p/ cobrir uma junta de dado comprimento (chapas de filme, com sobreposição
    já embutida no comprimento útil). Junta nula → 0; qualquer junta com comprimento → ao menos 1."""
    if not comprimento_junta_mm or comprimento_junta_mm <= 0 or filme_util_mm <= 0:
        return 0
    return max(1, math.ceil(comprimento_junta_mm / filme_util_mm))


def exposicoes_equipamento(comprimento_casco_mm: float, diametro_casco_mm: float,
                           n_seams_circ: int = 2,
                           filme_util_mm: float = FILME_UTIL_MM) -> dict:
    """Nº de exposições de RT do equipamento (estimativa, ASME Seção V Art.2):
    - longitudinal: 1 costura axial do casco, comprimento = comprimento do casco;
    - circunferencial: n_seams_circ costuras de topo (casco↔tampo/cabeçote), cada uma de
      comprimento π·D.
    Retorna {longitudinal, circunferencial, total}. Os defaults de filme são de chão de fábrica."""
    long = n_exposicoes(comprimento_casco_mm, filme_util_mm)
    circ_uma = n_exposicoes(math.pi * (diametro_casco_mm or 0), filme_util_mm)
    circ = max(0, int(n_seams_circ)) * circ_uma
    return {"longitudinal": long, "circunferencial": circ, "total": long + circ}
