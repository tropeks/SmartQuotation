"""
Registry das 67 operações do feixe — fiel às fórmulas da planilha ENGEMATEX.

Cada OpSpec encapsula: a qual item (EAP) pertence, se é aplicável (config), e o
cálculo do custo. 3 formatos:
  - geometria:    horas = f(geom, ProcessParameter) ; custo = horas × R$/h
  - tabela-faixa: horas = faixa(qtd, degraus) ; custo = horas × R$/h   (RESOLVIDO Q2)
  - serviço-fixo: custo = valor_fixo × aplicável

Rates (R$/h) aqui são os valores da planilha ENGEMATEX, usados para validar contra o
referencial. No produto vêm da cadeia de custos do tenant (wizard A1-c), editáveis.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Callable
from .feixe_inputs import FeixeInputs
from . import process_params as pp

ceil = math.ceil


def faixa(valor, degraus, acima):
    """Step-function editável: degraus=[(limite,horas)] ordenado; senão `acima`."""
    for limite, horas in degraus:
        if valor < limite:
            return horas
    return acima


@dataclass
class OpSpec:
    code: str
    item: str                       # código do item (EAP N1) ao qual pertence
    label: str
    compute: Callable[[FeixeInputs], float]   # → custo R$
    applicable: Callable[[FeixeInputs], bool] = lambda i: True
    group: str = ""


def _drill_method(inp):
    return pp.choose_drill_method(inp.num_furos)


# atalhos de geometria
def NF(i): return i.num_furos
def FC(i): return i.fator_correcao_mo
def AJ_OD(i, horas, rate): return horas * rate if abs(i.tubo_od_mm - 25.4) < 0.01 else 0.0

REGISTRY: list[OpSpec] = []
def _op(code, item, label, compute, applicable=lambda i: True, group=""):
    REGISTRY.append(OpSpec(code, item, label, compute, applicable, group))


# ===================== ESPELHOS (item ESP-01) =====================
_op("OP-ESP-USINAR", "ESP-01", "Espelhos - Usinar",
    lambda i: faixa(i.espelho_od_mm,
                    [(1000, 8 if not i.is_u else 4), (1200, 9 if not i.is_u else 5)],
                    10 if not i.is_u else 6) * FC(i) * (200 if i.espelho_od_mm > 1100 else 150),
    group="espelhos")
_op("OP-ESP-TRACAR-FUROS", "ESP-01", "Espelhos - Traçar Furos",
    lambda i: faixa(NF(i), [(400,2),(800,4),(1200,5),(2400,6),(3600,8)], 12) * FC(i) * 80,
    group="espelhos")
_op("OP-ESP-FURAR", "ESP-01", "Espelhos - Furar",
    lambda i: (lambda h: h*110 + AJ_OD(i,h,110))(ceil(i.espelho_esp_bruta_mm/pp.get("FURAR_ESPELHO",_drill_method(i),i.espelho_material)/60*NF(i))*FC(i)),
    group="espelhos")
_op("OP-ESP-ESCAREAR", "ESP-01", "Espelhos - Escarear",
    lambda i: ceil(pp.get("ESCAREAR_ESPELHO",pp.RADIAL)*NF(i)/60)*FC(i) * 110,
    group="espelhos")
_op("OP-ESP-ALARGAR", "ESP-01", "Espelhos - Alargar",
    lambda i: (lambda h: h*110 + AJ_OD(i,h,110))(ceil(i.espelho_esp_bruta_mm/pp.get("ALARGAR_ESPELHO",_drill_method(i),i.espelho_material)/60*NF(i))*FC(i)),
    applicable=lambda i: _drill_method(i) != pp.CNC,
    group="espelhos")
_op("OP-ESP-GROOVES", "ESP-01", "Espelhos - Grooves",
    lambda i: ceil(pp.get("GROOVES_ESPELHO",pp.RADIAL)*NF(i)/60)*FC(i) * 110,
    group="espelhos")
_op("OP-ESP-FUROS-TIR", "ESP-01", "Espelhos - Usinar Furos p/ Tirantes",
    lambda i: (1 if i.tirante_qty < 10 else 2)*FC(i) * 110,
    group="espelhos")
_op("OP-ESP-TRACAR-RASGOS", "ESP-01", "Espelhos - Traçar Rasgos",
    lambda i: faixa(i.num_rasgos, [(1,0),(2,1),(3,2),(4,3),(5,4),(6,5),(7,6)], 8)*FC(i) * 80,
    applicable=lambda i: i.num_rasgos > 0, group="espelhos")
_op("OP-ESP-USINAR-RASGOS", "ESP-01", "Espelhos - Usinar Rasgos",
    lambda i: faixa(i.num_rasgos, [(1,0),(2,4),(3,6),(4,8),(6,10)], 12)*FC(i) * (200 if i.espelho_od_mm>1000 else 150),
    applicable=lambda i: i.num_rasgos > 0, group="espelhos")
_op("OP-ESP-ACABAMENTO", "ESP-01", "Espelhos - Acabamento",
    lambda i: faixa(i.num_rasgos, [(2,2),(4,3)], 4)*FC(i) * 40,
    group="espelhos")
_op("OP-ESP-INSPECIONAR", "ESP-01", "Espelhos - Inspecionar",
    lambda i: (1 if i.num_rasgos<=1 else 2)*FC(i) * 110,
    group="espelhos")

# ===================== CHICANAS (item CHI-01) =====================
def _nchic(i): return i.chicana_qty + i.chapa_suporte_qty
_op("OP-CHI-TRACAR-REC", "CHI-01", "Chicanas - Traçar e Recortar",
    lambda i: faixa(_nchic(i), [(11,5),(31,7)], 8)*FC(i) * 90,
    applicable=lambda i: not i.chicana_corte_laser, group="chicanas")
_op("OP-CHI-TRACAR-FUROS", "CHI-01", "Chicanas - Traçar Furos",
    lambda i: faixa(i.n_tubos, [(300,2),(1000,3),(1500,4),(2000,5)], 6)*FC(i) * 80, group="chicanas")
_op("OP-CHI-FORMAR-PACOTE", "CHI-01", "Chicanas - Formar Pacote",
    lambda i: (1 if _nchic(i)<5 else (2 if i.esp_pacote_chicanas_mm<500 else 4))*FC(i) * 120, group="chicanas")
_op("OP-CHI-FURAR", "CHI-01", "Chicanas - Furar",
    lambda i: (lambda h: h*110 + AJ_OD(i,h,110))(ceil(i.esp_pacote_chicanas_mm/pp.get("FURAR_CHICANA",_drill_method(i),i.chicana_material)/60*i.n_tubos)*FC(i)),
    group="chicanas")
_op("OP-CHI-PREP-USINAR", "CHI-01", "Chicanas - Preparação p/ Usinar",
    lambda i: (1 if _nchic(i)<5 else (2 if i.esp_pacote_chicanas_mm<500 else (3 if i.esp_pacote_chicanas_mm<1000 else 4)))*FC(i) * 120, group="chicanas")
_op("OP-CHI-USINAR", "CHI-01", "Chicanas - Usinar",
    lambda i: (2 if _nchic(i)<5 else 3)*FC(i) * (200 if i.esp_pacote_chicanas_mm>1100 else 150), group="chicanas")
_op("OP-CHI-TRACAR-RECORTES", "CHI-01", "Chicanas - Traçar Recortes",
    lambda i: faixa(_nchic(i), [(11,5),(31,7)], 8)*FC(i) * 90,
    applicable=lambda i: not i.chicana_corte_laser, group="chicanas")
_op("OP-CHI-ESCAREAR", "CHI-01", "Chicanas - Escarear",
    lambda i: ceil(pp.get("ESCAREAR_CHICANA",pp.RADIAL)*(i.n_tubos*i.chicana_qty)/60)*FC(i) * 110, group="chicanas")
_op("OP-CHI-RECORTAR-ACAB", "CHI-01", "Chicanas - Recortar e Dar Acabamento",
    lambda i: faixa(_nchic(i), [(5,2),(10,4),(20,6),(30,8),(40,9)], 10)*FC(i) * 130,
    applicable=lambda i: not i.chicana_corte_laser, group="chicanas")
_op("OP-CHI-INSPECIONAR", "CHI-01", "Chicanas - Inspecionar",
    lambda i: 1*FC(i) * 110, group="chicanas")

# ===================== PREP / MONTAGEM (item MON-01) =====================
_op("OP-PREP-TIRANTES", "MON-01", "Preparar Tirantes",
    lambda i: (2 if i.tirante_qty<10 else 3)*FC(i) * 120, group="montagem")
_op("OP-PREP-ESPACADORES", "MON-01", "Preparar Espaçadores",
    lambda i: 3*FC(i) * 150, group="montagem")
_op("OP-MON-ESTRUTURA", "MON-01", "Montar Estrutura do Feixe",
    lambda i: 4*FC(i) * 160, group="montagem")
_op("OP-QUEBRA-JATO", "MON-01", "Quebra Jato",
    lambda i: 3*FC(i) * 90, group="montagem")
_op("OP-INTRODUZIR-TUBOS", "MON-01", "Introduzir os Tubos",
    lambda i: ceil(i.n_tubos*1.5/60)*FC(i) * (40 if not i.is_u else 200), group="montagem")
_op("OP-MON-ESP-FLUT", "MON-01", "Montar o Espelho Flutuante",
    lambda i: 3*FC(i) * 160, applicable=lambda i: i.n_espelhos>1, group="montagem")
_op("OP-MON-TUBOS", "MON-01", "Montar os Tubos",
    lambda i: ceil(i.n_tubos/50 if i.n_tubos<500 else (i.n_tubos/80 if i.n_tubos<1000 else i.n_tubos/100))*FC(i) * 40, group="montagem")
_op("OP-GABARITAR", "MON-01", "Gabaritar Tubos",
    lambda i: ceil((i.n_tubos/70 if i.n_tubos<200 else (i.n_tubos/120 if i.n_tubos<600 else i.n_tubos/170)) if not i.is_u else (i.n_tubos/20 if i.n_tubos<500 else i.n_tubos/30))*FC(i) * (40 if not i.is_u else 160), group="montagem")
_op("OP-MANDRILAR", "MON-01", "Mandrilar",
    lambda i: (lambda hh: hh*120 + (hh*pp.get("MANDRILAR_HM_FATOR",pp.MANUAL))*80)(ceil(pp.get("MANDRILAR",pp.MANUAL)*NF(i)/60/2)*FC(i)),
    group="montagem")
_op("OP-REBAIXAR", "MON-01", "Rebaixar e Dar Acabamento",
    lambda i: ceil(i.n_tubos/40 if i.n_tubos<500 else (i.n_tubos/60 if i.n_tubos<1000 else i.n_tubos/65))*FC(i) * 60, group="montagem")
_op("OP-SOLDAR-RAIZ", "MON-01", "Soldar Passe de Raiz",
    lambda i: ceil(NF(i)/pp.get("SOLDAR_RAIZ",pp.MANUAL))*FC(i) * 90, applicable=lambda i: i.solda_selagem, group="montagem")
_op("OP-LP-RAIZ", "MON-01", "Exame L.P. Passe Raiz",
    lambda i: 1 * 200, applicable=lambda i: i.solda_selagem, group="montagem")
_op("OP-SOLDAR-ACAB", "MON-01", "Soldar Passe de Acabamento",
    lambda i: ceil(NF(i)/pp.get("SOLDAR_ACABAMENTO",pp.MANUAL))*FC(i) * 90, applicable=lambda i: i.solda_selagem, group="montagem")
_op("OP-LP-ACAB", "MON-01", "Exame L.P. Passe Acabamento",
    lambda i: 1 * 200, applicable=lambda i: i.solda_selagem, group="montagem")
_op("OP-INSP-TUBOS", "MON-01", "Inspecionar Tubos Montados",
    lambda i: 1 * 110, group="montagem")

# ===================== TUBOS U (condicional) — item UTB-01 =====================
_op("OP-CURVAR-U", "UTB-01", "Curvamento de Tubos (ENGEMATEX)",
    lambda i: ceil(i.n_tubos/pp.get("CURVAR_TUBO_U",pp.MANUAL))*FC(i) * 160,
    applicable=lambda i: i.is_u, group="tubos_u")
_op("OP-PREP-U-TT", "UTB-01", "Preparar Tubos U p/ Tratamento Térmico",
    lambda i: 6*FC(i) * 160, applicable=lambda i: i.is_u, group="tubos_u")
_op("OP-TT-U", "UTB-01", "Tratamento Térmico Alívio Tensões - Tubos U",
    lambda i: 1 * 2000, applicable=lambda i: i.is_u, group="tubos_u")
_op("OP-LP-CURVAS-U", "UTB-01", "Exame L.P. nas Curvas dos Tubos U",
    lambda i: 12*FC(i) * 200, applicable=lambda i: i.is_u, group="tubos_u")

# ===================== BARRAS (item BAR-01) =====================
_op("OP-MON-BARRAS", "BAR-01", "Montar Barras",
    lambda i: faixa(i.n_barras_selagem_desliz, [(1,0),(4,2),(10,3)], 4)*FC(i) * 170,
    applicable=lambda i: i.n_barras_selagem_desliz>0, group="barras")
_op("OP-SOLDAR-BARRAS", "BAR-01", "Soldar Barras",
    lambda i: faixa(i.n_barras_selagem_desliz, [(1,0),(3,2),(4,3),(5,4),(7,5)], 6)*FC(i) * 90,
    applicable=lambda i: i.n_barras_selagem_desliz>0, group="barras")
_op("OP-ACAB-BARRAS", "BAR-01", "Dar Acabamento Barras",
    lambda i: faixa(i.n_barras_selagem_desliz, [(1,0),(3,2),(4,3),(5,4),(7,5)], 6)*FC(i) * 40,
    applicable=lambda i: i.n_barras_selagem_desliz>0, group="barras")
_op("OP-INSP-BARRAS", "BAR-01", "Inspecionar Barras Montadas",
    lambda i: 1 * 110, applicable=lambda i: i.n_barras_selagem_desliz>0, group="barras")

# ===================== ALÇA / BATENTE (item ALC-01) =====================
_op("OP-MON-ALCA", "ALC-01", "Montar Alça / Batente", lambda i: 3*FC(i) * 90, group="alca")
_op("OP-SOLDAR-ALCA", "ALC-01", "Soldar Alça / Batente", lambda i: 3*FC(i) * 90, group="alca")
_op("OP-ACAB-ALCA", "ALC-01", "Dar Acabamento Alça / Batente", lambda i: 2*FC(i) * 40, group="alca")
_op("OP-LP-ALCA", "ALC-01", "Exame L.P. na Solda Alça / Batente", lambda i: 1 * 80, group="alca")
_op("OP-INSP-ALCA", "ALC-01", "Inspecionar Alça / Batente", lambda i: 1 * 110, group="alca")

# ===================== ENSAIOS / FINAL (item END-01) =====================
_op("OP-TT-EQUIP", "END-01", "Tratamento Térmico Equipamento",
    lambda i: 1 * 5000, applicable=lambda i: i.tratamento_termico, group="ensaios")
_op("OP-LP-EQUIP", "END-01", "Exame de Líquido Penetrante",
    lambda i: 1 * 200, applicable=lambda i: i.tratamento_termico, group="ensaios")
_op("OP-DUREZA", "END-01", "Medir Dureza",
    lambda i: 1 * 150, applicable=lambda i: i.tratamento_termico, group="ensaios")
_op("OP-INSP-DIMENSIONAL", "END-01", "Inspeção Dimensional",
    lambda i: 1 * 600, group="ensaios")
_op("OP-PMI", "END-01", "P.M.I.",
    lambda i: 1 * 1500, applicable=lambda i: i.pmi, group="ensaios")
_op("OP-HIDRO", "END-01", "Teste Hidrostático",
    lambda i: 1 * 800, applicable=lambda i: i.teste_hidrostatico, group="ensaios")
_op("OP-TRANSP-PREP", "END-01", "Transporte - Preparação e Embalagem",
    lambda i: 1 * 150, group="ensaios")
_op("OP-TRANSP-ENT", "END-01", "Transporte: ENGEMATEX p/ Cliente",
    lambda i: i.custo_transporte, group="ensaios")

# ===================== ENGENHARIA (item ENG-01) =====================
_op("OP-PROJETO", "ENG-01", "Projeto - Detalhamento (Desenhos p/ Cliente)",
    lambda i: 1 * 1600, applicable=lambda i: i.projeto_detalhamento, group="engenharia")
_op("OP-PIT", "ENG-01", "Plano de Inspeção e Testes (PIT)",
    lambda i: 1 * 150, group="engenharia")
_op("OP-PS", "ENG-01", "Plano de Solda (PS)",
    lambda i: 1 * 250, group="engenharia")
_op("OP-DATABOOK", "ENG-01", "Data Book",
    lambda i: 1 * 250, group="engenharia")
_op("OP-INSP-Q", "ENG-01", "Inspeção Tipo Q",
    lambda i: 1 * 1500, applicable=lambda i: i.inspecao_q, group="engenharia")

# ===================== FERRAMENTAS (item FER-01) =====================
_op("OP-FERRAMENTAS", "FER-01", "Ferramentas",
    lambda i: 1 * 150, group="ferramentas")
_op("OP-EXPANDIDORES", "FER-01", "Expandidores",
    lambda i: ceil(NF(i)*0.65*2), group="ferramentas")
