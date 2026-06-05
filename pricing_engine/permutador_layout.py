"""
Validação de arranjo do feixe vs diâmetro do casco (TEMA, simplificado).

Endereça o achado #4 da auditoria adversarial: o usuário pode informar nº de tubos que
não cabe fisicamente no casco, gerando cotação de equipamento impossível de fabricar.

Estimativa do diâmetro do feixe (Outer Tube Limit) por área ocupada:
  pitch = pitch_ratio × OD_tubo  (típico 1,25)
  área por tubo (arranjo triangular 30°) ≈ 0,866 × pitch²
  D_OTL ≈ sqrt(4 × N × área_tubo / π) ≈ 1,05 × pitch × sqrt(N)  (+ folga periférica)
É ESTIMATIVA simplificada (não substitui tube-count table real / software de layout).
"""
from __future__ import annotations
import math

PITCH_RATIO_PADRAO = 1.25
FOLGA_CASCO_MM = 12.0          # folga típica feixe↔casco (espelho fixo/U): bypass + clearance
_AREA_TUBO = {"triangular": 0.866, "quadrado": 1.0}

# folga radial feixe↔casco por tipo de cabeçote traseiro TEMA (#5 agy). Cabeçote flutuante
# (P/S/T/W) exige folga muito maior p/ anel bipartido + flange de fechamento. Valores típicos.
FOLGA_POR_CABECOTE = {
    "L": 12.0, "M": 12.0, "N": 12.0, "U": 15.0,        # espelho fixo / feixe em U
    "P": 50.0, "S": 60.0, "T": 75.0, "W": 45.0,        # flutuante (anel bipartido / pull-through)
}


def folga_cabecote(letra) -> float:
    """Folga feixe↔casco (mm) conforme a letra do cabeçote traseiro TEMA."""
    return FOLGA_POR_CABECOTE.get((letra or "").upper(), FOLGA_CASCO_MM)


def d_feixe_min(n_tubos: int, od_tubo_mm: float, pitch_ratio: float = PITCH_RATIO_PADRAO,
                layout: str = "triangular") -> float:
    """Diâmetro estimado do feixe (OTL, mm) p/ acomodar n_tubos. Estimativa TEMA simplificada."""
    if n_tubos <= 0 or od_tubo_mm <= 0:
        return 0.0
    pitch = pitch_ratio * od_tubo_mm
    area_tubo = _AREA_TUBO.get(layout, 0.866) * pitch ** 2
    d_otl = math.sqrt(4.0 * n_tubos * area_tubo / math.pi)
    return d_otl + pitch          # + 1 passo de folga periférica


def check_layout(n_tubos: int, od_tubo_mm: float, d_casco_mm: float,
                 pitch_ratio: float = PITCH_RATIO_PADRAO, layout: str = "triangular",
                 cabecote: str | None = None) -> list[str]:
    """Avisos de arranjo (vazio = ok). NÃO bloqueia — apenas alerta o orçamentista.
    cabecote = letra TEMA do cabeçote traseiro (define a folga radial necessária, #5)."""
    avisos = []
    if not d_casco_mm:
        return avisos
    d_feixe = d_feixe_min(n_tubos, od_tubo_mm, pitch_ratio, layout)
    folga = folga_cabecote(cabecote)
    necessario = d_feixe + folga
    if necessario > d_casco_mm:
        avisos.append(
            f"Arranjo inviável: {n_tubos} tubos Ø{od_tubo_mm:g}mm (pitch {pitch_ratio:g}×OD, "
            f"{layout}) exigem feixe ≈ {d_feixe:.0f}mm + folga → casco ≥ {necessario:.0f}mm, "
            f"mas o casco informado tem Ø{d_casco_mm:.0f}mm. Aumente o diâmetro do casco ou "
            f"reduza o nº de tubos.")
    elif necessario > 0.92 * d_casco_mm:
        avisos.append(
            f"Arranjo apertado: feixe ≈ {d_feixe:.0f}mm vs casco Ø{d_casco_mm:.0f}mm "
            f"(< 8% de folga). Confira o tube-count real.")
    return avisos
