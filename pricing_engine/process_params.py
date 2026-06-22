"""
ProcessParameter — os "números mágicos" das fórmulas de horas (avanços, taxas, tempos).

Insight @WellToMcAt: NÃO são constantes fixas no código. São parâmetros editáveis por
(operação × método/máquina), versionados por data. Trocar radial→CNC = trocar o valor.

Regra de método (RESOLVIDO Q3): furação de espelhos/chicanas escolhe a máquina por limiar:
    nº furos ≤ THRESHOLD → radial ; > THRESHOLD → CNC   (THRESHOLD=600, editável)
O orçamentista pode dar override manual.
"""
from __future__ import annotations
from dataclasses import dataclass, field

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


# Catálogo inicial extraído das fórmulas da planilha (valores radial/atual ENGEMATEX).
# Avanços CNC confirmados com Wellington; alargamento usa fallback conservador radial.
CATALOG: dict[tuple[str, str], ProcessParameter] = {}


def _reg(op, metodo, valor, unidade, descr=""):
    CATALOG[(op, metodo)] = ProcessParameter(op, metodo, valor, unidade, descr)


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
# ALARGAR_ESPELHO CNC ainda PENDENTE: usa o avanço radial (70) como fallback conservador — mais
# lento → mais horas, nunca subestima o custo; trocar pelo valor real quando o Wellington confirmar.
_reg("ALARGAR_ESPELHO", CNC, 70, "mm/min", "PENDENTE: fallback = avanço radial conservador")


def choose_drill_method(num_holes: int, override: str | None = None,
                        threshold: int = DRILL_METHOD_THRESHOLD_HOLES) -> str:
    """Default automático radial/CNC por nº de furos; override manual vence."""
    if override:
        return override
    return RADIAL if num_holes <= threshold else CNC


def get(operacao: str, metodo: str) -> float:
    pp = CATALOG.get((operacao, metodo))
    if pp is None:
        raise KeyError(f"ProcessParameter ausente: ({operacao}, {metodo})")
    if pp.valor is None:
        raise NotImplementedError(
            f"ProcessParameter ({operacao},{metodo}) PENDENTE — definir valor com Wellington")
    return pp.valor
