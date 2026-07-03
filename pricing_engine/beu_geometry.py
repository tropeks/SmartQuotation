"""
Fórmulas de peso geométrico para componentes de casco/cabeçote (Permutador completo).

ρ é a densidade do material em kgf/mm³ — passada por componente (default = aço-carbono
7,85e-6; inox SS-300 ≈ 8,0e-6 etc. via pricing_engine.materials.density). Cada função
devolve o peso LÍQUIDO (kgf) de UMA peça. O peso BRUTO (base de custo, Opção A) = líquido
× (1 + perda). Validadas contra o gabarito BEU/BEM da planilha ENGEMATEX.

Famílias geometrizáveis: tubo · chapa_retangular (virola/divisora) · anel (flange
principal, anel de reforço) · pipe (pescoço de bocal) · disco (espelho/blank redondo,
peso bruto ≈ círculo) · disco_bocal (disco pequeno cortado de retalho QUADRADO de
chapa, peso bruto ≈ quadrado envolvente OD×OD — ver peso_disco_bocal) · tampo_2_1
(tampo elíptico). Itens comerciais (flange WN, conexões, porcas, suporte N-466) usam
peso/preço de catálogo — não são geometrizados aqui.
"""
from __future__ import annotations
import math

RHO = 7.85e-6  # kgf/mm³ (aço-carbono) — default quando a densidade do material não é dada

# fator de perda (bruto/líquido) por família — valores do Wellington (B): espelho e chicana
# (disco circular furado, recortado de chapa) perdem ~40%; tampo 20%; tubo/chapa 10%.
# (Componentes com dado de gabarito usam a perda real auto-calibrada; isto é o típico/fallback.)
PERDA_POR_FAMILIA = {
    "espelho": 1.40, "perfurado": 1.40, "disco": 1.40, "tampo_2_1": 1.20, "anel": 1.15,
    "chapa_retangular": 1.10, "tubo": 1.10, "pipe": 1.10,
}
PERDA_PADRAO = 1.10


def perda_familia(familia) -> float:
    """Fator bruto/líquido típico da família (fallback quando o seed não traz a perda real)."""
    return PERDA_POR_FAMILIA.get(familia, PERDA_PADRAO)

# CALIBRAÇÃO do tampo 2:1 (semielíptico), NÃO um fator de desenvolvimento físico.
# Vale exatamente 4/π = 1,2732. Como peso_tampo usa (π/4·od²·esp·ρ)·CALIB, o π/4 e o
# CALIB se cancelam → o tampo é tratado como uma CHAPA QUADRADA de lado od_disco
# (od_disco²·esp·ρ). É uma calibração empírica que casa o gabarito ENGEMATEX (tampo
# OD_DISCO 680,9 × esp 9,5 → 34,58 kgf líq); NÃO modela a aba reta (straight flange)
# nem o estiramento ASME. Limitação conhecida: calibrado a 1 ponto. Ver achado #3.
CALIB_TAMPO_2_1 = 4.0 / math.pi  # ≈ 1,2732


def peso_tubo(od, esp, comprimento, qtd=1, rho=RHO):
    """Tubo: coroa circular × comprimento. od/esp/comprimento em mm."""
    di = od - 2 * esp
    area = math.pi / 4 * (od ** 2 - di ** 2)
    return area * comprimento * rho * qtd


def peso_chapa_retangular(esp, largura, comprimento, qtd=1, rho=RHO):
    """Virola (chapa rolada), chapa divisora, chapa de impacto: prisma retangular."""
    return esp * largura * comprimento * rho * qtd


def peso_anel(od, id_, esp, qtd=1, rho=RHO):
    """Anel maciço (flange principal, anel de reforço): coroa circular × espessura."""
    area = math.pi / 4 * (od ** 2 - id_ ** 2)
    return area * esp * rho * qtd


def peso_pipe(od, esp, comprimento, qtd=1, rho=RHO):
    """Pescoço de bocal (tubo de processo SA-106): coroa × comprimento."""
    return peso_tubo(od, esp, comprimento, qtd, rho)


def peso_disco(od, esp, qtd=1, rho=RHO):
    """Disco maciço (espelho, chapa suporte): círculo × espessura."""
    area = math.pi / 4 * od ** 2
    return area * esp * rho * qtd


def peso_disco_bocal(od, esp, qtd=1, rho=RHO):
    """Disco BOCAL pequeno (chapa Φ<OD>, recortado de retalho QUADRADO de chapa —
    ao contrário do espelho/tampo, que é um blank forjado/redondo cotado direto).
    O peso BRUTO (Opção A, cobra a perda) é o do quadrado envolvente OD×OD, não o
    do círculo: confirmado no manuscrito OF-3683 (DES 17.263-04-2, IT.4/IT.5/IT.6 —
    "CHAPA Φ<OD>X<ESP>"), onde peso_bruto/preço reconcilia com OD² e não com
    π/4·OD² (razão observada 41,978/32,1 ≈ 1,307 ≈ 4/π). Família distinta de
    'disco' para não afetar espelhos/tampos (blanks redondos, sem esse refugo)."""
    return od * od * esp * rho * qtd


def peso_tampo_2_1(od_disco, esp, qtd=1, rho=RHO):
    """Tampo elíptico 2:1: peso ≈ chapa quadrada de lado od_disco (ver CALIB_TAMPO_2_1)."""
    area = math.pi / 4 * od_disco ** 2
    return area * esp * rho * CALIB_TAMPO_2_1 * qtd


def peso_barra(esp, largura, comprimento, qtd=1, rho=RHO):
    """Barra chata (selagem, deslizamento): igual chapa retangular."""
    return peso_chapa_retangular(esp, largura, comprimento, qtd, rho)


# despacho por família → função + nomes de dimensão esperados no seed
GEOMETRIZAVEIS = {
    "tubo": (peso_tubo, ("OD", "ESP.", "COMPR.")),
    "pipe": (peso_pipe, ("OD", "ESP.", "COMPR.")),
    "chapa_retangular": (peso_chapa_retangular, ("ESP.", "LARGURA", "COMPR.")),
    "anel": (peso_anel, ("OD", "ID", "ESP.")),
    "disco": (peso_disco, ("OD", "ESP.")),
    # disco pequeno cortado de retalho quadrado (bocal) — ver peso_disco_bocal.
    "disco_bocal": (peso_disco_bocal, ("OD", "ESP.")),
    # espelho = disco maciço furado: peso BRUTO da chapa-disco original (os furos saem como
    # refugo, capturados na perda). Fora do gate geométrico estrito (peso_liq desconta furos).
    "espelho": (peso_disco, ("OD", "ESP.")),
    # chicana = recorte de chapa (blank = bounding box LARG×COMPR×ESP); recorte+furos = refugo.
    "perfurado": (peso_chapa_retangular, ("ESP.", "LARG.", "COMPR.")),
    "tampo_2_1": (peso_tampo_2_1, ("OD DISCO", "ESP.")),
}


def peso_liquido_geom(familia, dims, rho=RHO):
    """Peso líquido (kgf, 1 peça) de um material geometrizável a partir das dimensões do
    seed, com densidade rho (default aço-carbono). None se a família não é geometrizável
    ou faltam dimensões."""
    spec = GEOMETRIZAVEIS.get(familia)
    if not spec:
        return None
    func, campos = spec

    def norm(k):
        return k.strip().rstrip(".").upper()

    # índice tolerante: ignora ponto/caixa/espaço; 'LARG.' casa 'LARGURA' por prefixo
    idx = {norm(k): v for k, v in dims.items()}

    def lookup(campo):
        nc = norm(campo)
        if nc in idx:
            return idx[nc]
        for k, v in idx.items():       # prefixo (LARG → LARGURA)
            if k.startswith(nc[:4]) or nc.startswith(k[:4]):
                return v
        return None

    try:
        args = [float(lookup(c)) for c in campos]
    except (TypeError, ValueError):
        return None
    return func(*args, qtd=1, rho=rho)
