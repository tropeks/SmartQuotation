"""
Pesos dos componentes do feixe — computados da geometria (geometria → volume → peso).

Geometria do caso real (planilha, seção MATÉRIA PRIMA). Cada componente vira um Item (N1)
da EAP com sua MatériaPrima (N2). Pesos inequívocos implementados; os ambíguos sinalizados.

Formas:
  disco cheio:      A = π/4 · OD²
  barra redonda:    A = π/4 · OD²              (× comprimento)
  barra chata:      A = largura · espessura    (× comprimento)
  tubo:             ver dimensions.tube_*       (espaçador BWG)
  segmento chicana: disco − corte  → PENDENTE forma exata (ver TODO)
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from . import dimensions as dim, materials as mat


@dataclass
class CompSpec:
    codigo: str
    descricao: str
    material: str
    forma: str
    qtd: float
    # geometria (mm) — campos usados variam por forma
    od_mm: float = 0.0
    esp_mm: float = 0.0
    comp_mm: float = 0.0
    larg_mm: float = 0.0
    od_spec: str = ""      # p/ tubo: '3/4"'
    wall_spec: str = ""    # p/ tubo: 'BWG 14'
    rkg: float = 0.0
    # chicana (TEMA RCB-4):
    cut_remaining_mm: float = 0.0   # "CORTE": altura que sobra → hc = od - cut_remaining
    n_tubes: int = 0                # nº tubos do feixe (p/ desconto de furos, peso líquido)
    tube_od_mm: float = 0.0         # OD do tubo (p/ d_furo)
    nota: str = ""


def disco_cheio_kg(od_mm, esp_mm, dens, qtd=1):
    return math.pi / 4 * od_mm**2 * esp_mm * dens * qtd


def barra_redonda_kg(od_mm, comp_mm, dens, qtd=1):
    return math.pi / 4 * od_mm**2 * comp_mm * dens * qtd


def barra_chata_kg(larg_mm, esp_mm, comp_mm, dens, qtd=1):
    return larg_mm * esp_mm * comp_mm * dens * qtd


def od_inch_to_mm(spec: str) -> float:
    return dim.tube_od_mm(spec)


def peso_liquido_componente(c: CompSpec) -> float:
    """Peso LÍQUIDO (instalado): desconta furos dos tubos (chicana/espelho).
    Para custo usa-se o BRUTO (peso_componente); este é informativo (peso real do
    equipamento p/ içamento/NR-13). A diferença bruto-líquido = refugo de material.
    TEMA RCB-4 (spec @WellToMcAt): Mliq = (A_bruta - N_furos·π·d_furo²/4)·t·ρ.
    """
    bruto, st = peso_componente(c)
    if st != "ok" or not c.n_tubes or not c.tube_od_mm:
        return bruto                      # sem furos a descontar
    d = mat.density(c.material)
    d_furo = c.tube_od_mm + 0.4           # folga TEMA RCB-4.1 (~0.4mm)
    if c.forma == "disco":                # espelho: N furos = N tubos
        n_furos = c.n_tubes
    elif c.forma == "chicana":            # chicana: N_tubos_chicana ≈ N_total × (A_bruta/A_disco)
        Dbi = c.od_mm
        hc = Dbi - c.cut_remaining_mm if c.cut_remaining_mm else 0.0
        if hc <= 0:
            n_furos = c.n_tubes
        else:
            theta = 2 * math.acos(1 - 2 * hc / Dbi)
            A_seg = (Dbi**2 / 8) * (theta - math.sin(theta))
            frac = (math.pi / 4 * Dbi**2 - A_seg) / (math.pi / 4 * Dbi**2)
            n_furos = round(c.n_tubes * frac)
    else:
        return bruto
    vol_furos = n_furos * math.pi / 4 * d_furo**2 * c.esp_mm
    return bruto - vol_furos * d * c.qtd


def peso_componente(c: CompSpec) -> tuple[float, str]:
    """Retorna (peso_BRUTO_kg, status). Bruto = base de custo (Opção A: cobra perdas).
    status='ok' ou 'PENDENTE: <motivo>'."""
    d = mat.density(c.material)
    f = c.forma
    if f == "tubo":
        w = dim.tube_weight_kg(c.od_spec, c.wall_spec, c.comp_mm, int(c.qtd), d)
        return w, "ok"
    if f == "disco":
        return disco_cheio_kg(c.od_mm, c.esp_mm, d, c.qtd), "ok"
    if f == "barra_redonda":
        od = od_inch_to_mm(c.od_spec) if c.od_spec else c.od_mm
        return barra_redonda_kg(od, c.comp_mm, d, c.qtd), "ok"
    if f == "barra_chata":
        return barra_chata_kg(c.larg_mm, c.esp_mm, c.comp_mm, d, c.qtd), "ok"
    if f == "porca":
        # envelope hex aproximado: ~1.6·OD largura, ~0.8·OD altura
        od = od_inch_to_mm(c.od_spec) if c.od_spec else c.od_mm
        vol1 = math.pi / 4 * (1.6 * od) ** 2 * (0.8 * od)
        return vol1 * d * c.qtd, "ok"
    if f == "chicana":
        # Chicana segmentada simples (TEMA RCB-4, spec @WellToMcAt).
        # CORTE = altura que sobra → hc (altura do segmento cortado) = od - cut_remaining.
        Dbi = c.od_mm
        hc = Dbi - c.cut_remaining_mm if c.cut_remaining_mm else 0.0
        if hc <= 0:                      # sem corte (chapa suporte = disco cheio)
            A_bruta = math.pi / 4 * Dbi**2
        else:
            theta = 2 * math.acos(1 - 2 * hc / Dbi)
            A_seg = (Dbi**2 / 8) * (theta - math.sin(theta))
            A_bruta = math.pi / 4 * Dbi**2 - A_seg
        # CUSTO usa peso BRUTO (chapa comprada, antes de furar) — ver pergunta de
        # reconciliação custo-vs-peso-físico. Desconto de furos (peso líquido) fica
        # disponível mas não aplicado ao custo por ora.
        area = A_bruta
        return area * c.esp_mm * d * c.qtd, "ok"
    return 0.0, f"PENDENTE: forma '{f}' não implementada"


# --- Componentes do caso real 136 tubos (da seção MATÉRIA PRIMA da planilha) ---
def feixe_136_componentes() -> list[CompSpec]:
    return [
        CompSpec("TUB-01", "Tubos de Troca Térmica", "SA-179", "tubo", 136,
                 od_spec='3/4"', wall_spec="BWG 14", comp_mm=6096, rkg=13.5),
        CompSpec("ESP-2a", "Espelho Fixo", "SA-516 GR 70", "disco", 1,
                 od_mm=475, esp_mm=44.5, rkg=6.5, n_tubes=136, tube_od_mm=19.05),
        CompSpec("ESP-2b", "Espelho Flutuante", "SA-516 GR 70", "disco", 1,
                 od_mm=412, esp_mm=44.5, rkg=6.5, n_tubes=136, tube_od_mm=19.05),
        CompSpec("CHI-3", "Chicanas Transversais", "SA-36", "chicana", 18,
                 od_mm=416.8, esp_mm=12.5, rkg=6.5,
                 cut_remaining_mm=300, n_tubes=136, tube_od_mm=19.05),
        CompSpec("SUP-4", "Chapa Suporte", "SA-36", "chicana", 1,
                 od_mm=416.8, esp_mm=12.5, rkg=6.5,
                 cut_remaining_mm=0, n_tubes=136, tube_od_mm=19.05),  # disco cheio (hc=0)
        CompSpec("TIR-7", "Tirantes", "SAE-1020", "barra_redonda", 12,
                 od_spec='3/8"', comp_mm=6000, rkg=4.5),
        CompSpec("BSE1-9.1", "Barras de Selagem (1)", "SA-36", "barra_chata", 2,
                 larg_mm=50, esp_mm=6.3, comp_mm=6000, rkg=4.5),
        CompSpec("BSE2-9.2", "Barras de Selagem (2)", "SA-36", "barra_chata", 2,
                 larg_mm=75, esp_mm=6.3, comp_mm=6000, rkg=4.5),
        CompSpec("BDE-10", "Barras de Deslizamento", "SA-36", "barra_chata", 2,
                 larg_mm=50, esp_mm=12.5, comp_mm=6000, rkg=4.5),
        CompSpec("IMP-11", "Chapa de Impacto", "SA-36", "barra_chata", 1,
                 larg_mm=250, esp_mm=6.3, comp_mm=250, rkg=6.5),
        CompSpec("ESC-6a", "Espaçador BWG", "SA-214", "tubo", 12,
                 od_spec='3/4"', wall_spec="BWG 14", comp_mm=6096, rkg=9,
                 nota="PENDENTE: comprimento real do espaçador (planilha usa 6096?)"),
        # itens menores
        CompSpec("ALC-16", "Alça", "SA-36", "barra_chata", 2,
                 larg_mm=37, esp_mm=12.5, comp_mm=30, rkg=10),
        CompSpec("PLG1-19", "Plugues (1)", "AISI-304", "barra_redonda", 2,
                 od_spec='5/8"', comp_mm=25, rkg=50),
        CompSpec("PLG2-20", "Plugues (2)", "AISI-304", "barra_redonda", 2,
                 od_spec='3/4"', comp_mm=30, rkg=50),
        CompSpec("OLH1-W1", "Olhais (1)", "SAE-1045", "barra_redonda", 2,
                 od_spec='5/8"', comp_mm=200, rkg=50),
        CompSpec("OLH2-W2", "Olhais (2)", "SAE-1045", "barra_redonda", 2,
                 od_spec='3/4"', comp_mm=220, rkg=50),
        CompSpec("POR-8", "Porcas Sextavadas", "SA-194 GR 2H", "porca", 24,
                 od_spec='3/8"', rkg=0.5, nota="porca: peso por catálogo ~aprox"),
    ]
