"""
ProcessParameter — os "números mágicos" das fórmulas de horas (avanços, taxas, tempos).

Insight @WellToMcAt: NÃO são constantes fixas no código. São parâmetros editáveis por
(operação × método/máquina), versionados por data. Trocar radial→CNC = trocar o valor.

Regra de método (RESOLVIDO Q3): furação de espelhos/chicanas escolhe a máquina por limiar:
    nº furos ≤ THRESHOLD → radial ; > THRESHOLD → CNC   (THRESHOLD=600, editável)
O orçamentista pode dar override manual.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

RADIAL = "radial"
CNC = "cnc"
MANUAL = "manual"

# limiar editável (por tenant) p/ escolha automática radial vs CNC na furação
DRILL_METHOD_THRESHOLD_HOLES = 600


@dataclass(frozen=True)
class ProcessParameter:
    operacao: str        # ex: "FURAR_ESPELHO"
    metodo: str          # radial | cnc | manual
    valor: float         # ex: 40 (mm/min) ou 0.5 (min/furo)
    unidade: str         # "mm/min", "min/furo", "juntas/h", "tubos/h", "fator"
    descricao: str = ""
    material: str | None = None


# Catálogo inicial extraído das fórmulas da planilha (valores radial/atual ENGEMATEX).
# Avanços CNC confirmados com Wellington. Em CNC não há etapa de alargamento; essa regra
# fica nas fórmulas de operação, não como ProcessParameter fake.
CATALOG: dict[tuple[str, str, str | None], ProcessParameter] = {}
_OVERRIDES: ContextVar[dict[tuple[str, str, str | None], float] | None] = ContextVar(
    "process_param_overrides", default=None
)


def _reg(op, metodo, valor, unidade, descr="", material=None):
    CATALOG[(op, metodo, material)] = ProcessParameter(op, metodo, valor, unidade, descr, material)


# --- avanços / taxas de usinagem (radial = baseline da planilha) ---
_reg("FURAR_ESPELHO", RADIAL, 40, "mm/min", "avanço furadeira radial (esp/40/60)")
_reg("ALARGAR_ESPELHO", RADIAL, 70, "mm/min", "avanço alargamento (esp/70/60)")
_reg("FURAR_CHICANA", RADIAL, 36, "mm/min", "avanço furação pacote chicanas (esp/36/60)")
_reg("ESCAREAR_ESPELHO", RADIAL, 0.25, "min/furo", "tempo por furo")
_reg("GROOVES_ESPELHO", RADIAL, 0.35, "min/furo", "tempo por furo")
_reg("ESCAREAR_CHICANA", RADIAL, 0.10, "min/furo", "tempo por furo")
_reg("MANDRILAR", MANUAL, 0.5, "min/furo", "tempo por furo (HH)")
_reg("MANDRILAR_HM_FATOR", MANUAL, 3.0, "fator", "horas_máquina = fator × horas_homem")
_reg("SOLDAR_RAIZ", MANUAL, 40, "juntas/h", "taxa de soldagem passe raiz")
_reg("SOLDAR_ACABAMENTO", MANUAL, 40, "juntas/h", "taxa de soldagem passe acabamento")
_reg("CURVAR_TUBO_U", MANUAL, 20, "tubos/h", "curvamento ENGEMATEX")
_reg("INTRODUZIR_TUBOS", MANUAL, 1.5, "min/tubo", "")
# CNC — avanços validados pelo PE (Wellington, 2026-06-19):
_reg("FURAR_ESPELHO", CNC, 97.56, "mm/min", "avanço furação espelho CNC (Wellington 2026-06-19)")
_reg("FURAR_CHICANA", CNC, 83.34, "mm/min", "avanço furação chicanas CNC (Wellington 2026-06-19)")


def choose_drill_method(num_holes: int, override: str | None = None,
                        threshold: int = DRILL_METHOD_THRESHOLD_HOLES) -> str:
    """Default automático radial/CNC por nº de furos; override manual vence."""
    if override:
        return override
    return RADIAL if num_holes <= threshold else CNC


@contextmanager
def override(catalog: dict[tuple[str, str, str | None], float] | None):
    """Aplica overrides temporários vindos do tenant sem acoplar o motor ao Django."""
    token = _OVERRIDES.set(catalog or None)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


def get(operacao: str, metodo: str, material: str | None = None) -> float:
    material = material or None
    overrides = _OVERRIDES.get()
    if overrides:
        if material is not None and (operacao, metodo, material) in overrides:
            return overrides[(operacao, metodo, material)]
        if (operacao, metodo, None) in overrides:
            return overrides[(operacao, metodo, None)]

    pp = None
    if material is not None:
        pp = CATALOG.get((operacao, metodo, material))
    if pp is None:
        pp = CATALOG.get((operacao, metodo, None))
    if pp is None:
        raise KeyError(f"ProcessParameter ausente: ({operacao}, {metodo}, {material})")
    if pp.valor is None:
        raise NotImplementedError(
            f"ProcessParameter ({operacao},{metodo},{material}) sem valor numérico")
    return pp.valor
