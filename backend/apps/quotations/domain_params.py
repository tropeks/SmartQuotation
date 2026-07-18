"""
Helpers de domínio dos parâmetros configuráveis (Config de Engenharia v1).

São funções PURAS (sem Django) que espelham EXATAMENTE a conversão feita no front-end
(Alpine) do data sheet, para que o back-end valide/persista o mesmo número que o usuário vê.
O motor (pricing_engine) continua puro: estes helpers vivem na camada Django (form/validator),
convertendo % → mm ANTES de o valor entrar em FeixeInputs.
"""
from __future__ import annotations


def baffle_cut_pct_to_mm(pct: float, d_interno_casco: float) -> float:
    """Corte de chicana (baffle cut) em % do Ø interno do casco → altura RESTANTE em mm.

    ATENÇÃO à semântica do campo do motor: `chicana_cut_remaining_mm` é a altura que SOBRA
    (o motor faz `hc = OD − restante`). O baffle cut TEMA é a JANELA cortada como % de D
    (tipicamente 15–45%). Logo:  restante = D × (1 − pct/100).

    (Isto diverge da fórmula literal `mm = pct/100 × D` do plano: aquela trataria o campo como
    a altura cortada, o que colocaria o job de referência — restante 300 mm, OD 416,8 → 28% de
    corte — em ~75% de corte, fora de qualquer faixa física. Ver relatório/decisão de design.)
    """
    return round(float(d_interno_casco) * (1.0 - float(pct) / 100.0), 1)


def baffle_cut_mm_to_pct(mm: float, d_interno_casco: float) -> float:
    """Inverso: altura restante (mm) → baffle cut % do Ø interno. 0 se o Ø não estiver definido."""
    d = float(d_interno_casco)
    if d <= 0:
        return 0.0
    return round((d - float(mm)) / d * 100.0, 1)


def desenvolvido_tubo_mm(comp_mm: float, is_u: bool) -> float:
    """Comprimento DESENVOLVIDO do tubo (mm). No feixe em U o tubo é uma peça única dobrada
    ao meio → o desenvolvido ≈ 2 × a perna reta (heurística; a curva é desprezada).
    No feixe reto o desenvolvido é o próprio comprimento."""
    comp = float(comp_mm)
    return comp * 2.0 if is_u else comp


def precisa_emenda(comp_mm: float, is_u: bool, standard_lengths_mm) -> bool:
    """True se o desenvolvido do tubo passa do MAIOR comprimento comercial padrão → emenda."""
    lengths = [float(x) for x in (standard_lengths_mm or []) if float(x) > 0]
    if not lengths:
        return False
    return desenvolvido_tubo_mm(comp_mm, is_u) > max(lengths)


def u_bend_min_radius_mm(od_mm: float, factor: float) -> float:
    """Raio mínimo admissível da curva em U = fator × OD do tubo (TEMA RCB-2.3)."""
    return round(float(factor) * float(od_mm), 2)
