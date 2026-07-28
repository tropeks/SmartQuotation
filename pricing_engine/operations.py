"""
Fórmulas de horas por operação — fiéis às fórmulas da planilha ENGEMATEX.

Cada função recebe geometria + ProcessParameter e devolve HORAS (homem-hora).
ROUNDUP da planilha = math.ceil. O fator de correção de MO é aplicado pelo chamador.

Implementadas aqui: operações cost-driver validáveis contra o referencial.
As step-functions (usinar/traçar) ficam como TABELA DE FAIXA editável (RESOLVIDO Q2) —
representadas por `faixa()`; valores default lidos da planilha.
"""
from __future__ import annotations
import math
from . import process_params as pp


def furar_espelho_horas(num_furos: int, esp_espelho_mm: float, metodo: str | None = None,
                        material: str | None = None) -> float:
    """ESPELHOS - FURAR: ceil(esp/avanço/60 × furos). Avanço = ProcessParameter (radial/CNC)."""
    metodo = pp.choose_drill_method(num_furos, override=metodo)
    avanco = pp.get("FURAR_ESPELHO", metodo, material)        # mm/min
    return math.ceil(esp_espelho_mm / avanco / 60 * num_furos)


def alargar_espelho_horas(num_furos: int, esp_espelho_mm: float, metodo: str | None = None,
                          material: str | None = None) -> float:
    metodo = pp.choose_drill_method(num_furos, override=metodo)
    if metodo == pp.CNC:
        return 0
    avanco = pp.get("ALARGAR_ESPELHO", metodo, material)
    return math.ceil(esp_espelho_mm / avanco / 60 * num_furos)


def escarear_espelho_horas(num_furos: int) -> float:
    t = pp.get("ESCAREAR_ESPELHO", pp.RADIAL)       # min/furo
    return math.ceil(t * num_furos / 60)


def grooves_espelho_horas(num_furos: int) -> float:
    t = pp.get("GROOVES_ESPELHO", pp.RADIAL)
    return math.ceil(t * num_furos / 60)


def furar_chicana_horas(esp_pacote_mm: float, num_tubos: int, metodo: str | None = None,
                        material: str | None = None) -> float:
    """CHICANAS - FURAR: ceil(esp_pacote/avanço/60 × nº_tubos)."""
    metodo = pp.choose_drill_method(num_tubos, override=metodo)
    avanco = pp.get("FURAR_CHICANA", metodo, material)
    return math.ceil(esp_pacote_mm / avanco / 60 * num_tubos)


def escarear_chicana_horas(num_furos_chicana: int) -> float:
    t = pp.get("ESCAREAR_CHICANA", pp.RADIAL)
    return math.ceil(t * num_furos_chicana / 60)


def mandrilar_horas_hh(num_furos: int) -> float:
    """MANDRILAR: horas_HH = ceil(0.5 × furos /60 /2)."""
    t = pp.get("MANDRILAR", pp.MANUAL)              # min/furo
    return math.ceil(t * num_furos / 60 / 2)


def mandrilar_horas_hm(horas_hh: float) -> float:
    """horas_máquina = fator × horas_homem (planilha: BD=AN×3)."""
    return horas_hh * pp.get("MANDRILAR_HM_FATOR", pp.MANUAL)


def soldar_horas(num_juntas: int, passe: str = "raiz") -> float:
    """SOLDAR passe raiz/acabamento: ceil(juntas / taxa)."""
    op = "SOLDAR_RAIZ" if passe == "raiz" else "SOLDAR_ACABAMENTO"
    taxa = pp.get(op, pp.MANUAL)                    # juntas/h
    return math.ceil(num_juntas / taxa)


def curvar_tubo_u_horas(num_tubos: int) -> float:
    taxa = pp.get("CURVAR_TUBO_U", pp.MANUAL)       # tubos/h
    return math.ceil(num_tubos / taxa)


def faixa(valor: float, degraus: list[tuple[float, float]], acima: float) -> float:
    """Tabela de faixa editável (step-function). degraus=[(limite, horas)], ordenado.
    Retorna horas do primeiro degrau cujo limite > valor; senão `acima`."""
    for limite, horas in degraus:
        if valor < limite:
            return horas
    return acima
