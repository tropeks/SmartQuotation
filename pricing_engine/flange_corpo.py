"""
Flange de corpo (girth flange casco↔cabeçote) — espessura mínima por ASME VIII Div.1,
Apêndice Mandatório 2 (regras de flange aparafusado), tipo ANEL SOLTO sem pescoço.

É o flange "FLANGE PRINCIPAL" (família anel) dos seeds BEU/BEM — custom, não-catálogo. O motor
estima a espessura exigida pela pressão/diâmetro/material e ALERTA se a referência do gabarito
não cobrir a condição de projeto (espelha o A1 do casco, UG-27).

LIMITAÇÃO (declarada na UI): gaxeta e parafusos usam DEFAULTS de engenharia (gaxeta espiralada
m=3,0 / y=69 MPa; geometria de furação proporcional ao flange). A matemática do Apêndice 2 é
exata; os defaults de gaxeta/parafuso devem ser confirmados pela engenharia (Wellington).
"""
from __future__ import annotations

import math

# defaults de gaxeta (ASME VIII Tabela 2-5.1): espiralada metálica → m≈3,0 ; y≈69 MPa.
GASKET_M_DEFAULT = 3.0
GASKET_Y_DEFAULT = 69.0          # MPa
GASKET_B_DEFAULT = 8.0           # largura efetiva de assentamento b (mm) — estimativa


def fator_Y(K: float) -> float | None:
    """Fator de tensão de flange Y (ASME VIII Apêndice 2-3) em função de K = A/B (OD/bore)."""
    if K <= 1.0:
        return None
    return (1.0 / (K - 1.0)) * (0.66845 + 5.71690 * (K * K * math.log10(K)) / (K * K - 1.0))


def t_min_flange_corpo(pressao_bar: float, bore_mm: float, od_mm: float, s_mpa: float,
                       gasket_m: float = GASKET_M_DEFAULT, gasket_y: float = GASKET_Y_DEFAULT,
                       gasket_b: float = GASKET_B_DEFAULT) -> float | None:
    """Espessura mínima do flange de corpo (anel solto) por ASME VIII Apêndice 2.

    Retorna a espessura (mm) que satisfaz a tensão tangencial admissível na operação E no
    assentamento da gaxeta (a maior das duas). None se entradas inválidas.

    Geometria de gaxeta/parafusos derivada proporcionalmente da largura radial do flange
    (defaults documentados): gaxeta a ~25% e furação a ~65% do vão bore→OD.
    """
    if not (pressao_bar and bore_mm and od_mm and s_mpa) or od_mm <= bore_mm:
        return None
    p = pressao_bar * 0.1                       # bar → MPa
    B = bore_mm                                 # diâmetro interno do flange (bore)
    A = od_mm                                   # diâmetro externo do flange
    K = A / B
    Y = fator_Y(K)
    if Y is None:
        return None
    vao = A - B                                 # largura radial (diâmetros) do anel
    G = B + 0.25 * vao                          # diâmetro de reação da gaxeta (estimativa)
    C = B + 0.65 * vao                          # diâmetro do círculo de furação (estimativa)
    b = gasket_b
    # cargas (Apêndice 2-5)
    H = 0.785 * G * G * p                        # força hidrostática total
    Hp = 2.0 * b * math.pi * G * gasket_m * p    # compressão na gaxeta (operação)
    Wm1 = H + Hp                                 # carga de parafuso — operação
    Wm2 = math.pi * b * G * gasket_y             # carga de parafuso — assentamento
    # momentos (anel solto, braços Apêndice 2-6)
    HD = 0.785 * B * B * p
    hD = (C - B) / 2.0
    HG = Wm1 - H
    hG = (C - G) / 2.0
    HT = H - HD
    hT = (hD + hG) / 2.0
    Mo_op = HD * hD + HT * hT + HG * hG          # momento de operação
    Mo_seat = Wm2 * hG                           # momento de assentamento (Ab ≈ Am)
    # tensão tangencial do anel ST = Y·Mo/(t²·B) ≤ S  → t = sqrt(Y·Mo/(S·B))
    t_op = math.sqrt(Y * Mo_op / (s_mpa * B))
    t_seat = math.sqrt(Y * Mo_seat / (s_mpa * B))
    return max(t_op, t_seat)
