"""
Fórmulas de peso geométrico para componentes de casco/cabeçote (Permutador completo).

Aço-carbono ρ = 7,85e-6 kgf/mm³. Cada função devolve o peso LÍQUIDO (kgf) de UMA peça.
O peso BRUTO (base de custo, Opção A) = líquido × (1 + perda). Validadas contra o
gabarito BEU da planilha ENGEMATEX (pricing_engine/seeds/beu_materiais.json).

Famílias geometrizáveis: tubo · chapa_retangular (virola/divisora) · anel (flange
principal, anel de reforço) · pipe (pescoço de bocal) · disco (espelho/chapa suporte) ·
tampo_2_1 (tampo elíptico). Itens comerciais (flange WN, conexões, porcas, suporte
N-466) usam peso/preço de catálogo — não são geometrizados aqui.
"""
from __future__ import annotations
import math

RHO = 7.85e-6  # kgf/mm³ (aço-carbono)

# Tampo 2:1 (semielíptico): o disco-blank é maior que o OD do tampo. Fator de
# desenvolvimento médio (área desenvolvida / área do disco nominal) ≈ 1,27 — calibrado
# contra o gabarito (tampo OD_DISCO 680,9 × esp 9,5 → 34,58 kgf líq).
FATOR_DESENV_TAMPO_2_1 = 1.273


def peso_tubo(od, esp, comprimento, qtd=1):
    """Tubo: coroa circular × comprimento. od/esp/comprimento em mm."""
    di = od - 2 * esp
    area = math.pi / 4 * (od ** 2 - di ** 2)
    return area * comprimento * RHO * qtd


def peso_chapa_retangular(esp, largura, comprimento, qtd=1):
    """Virola (chapa rolada), chapa divisora, chapa de impacto: prisma retangular."""
    return esp * largura * comprimento * RHO * qtd


def peso_anel(od, id_, esp, qtd=1):
    """Anel maciço (flange principal, anel de reforço): coroa circular × espessura."""
    area = math.pi / 4 * (od ** 2 - id_ ** 2)
    return area * esp * RHO * qtd


def peso_pipe(od, esp, comprimento, qtd=1):
    """Pescoço de bocal (tubo de processo SA-106): coroa × comprimento."""
    return peso_tubo(od, esp, comprimento, qtd)


def peso_disco(od, esp, qtd=1):
    """Disco maciço (espelho, chapa suporte): círculo × espessura."""
    area = math.pi / 4 * od ** 2
    return area * esp * RHO * qtd


def peso_tampo_2_1(od_disco, esp, qtd=1):
    """Tampo elíptico 2:1: disco-blank desenvolvido × espessura."""
    area = math.pi / 4 * od_disco ** 2
    return area * esp * RHO * FATOR_DESENV_TAMPO_2_1 * qtd


def peso_barra(esp, largura, comprimento, qtd=1):
    """Barra chata (selagem, deslizamento): igual chapa retangular."""
    return peso_chapa_retangular(esp, largura, comprimento, qtd)


# despacho por família → função + nomes de dimensão esperados no seed
GEOMETRIZAVEIS = {
    "tubo": (peso_tubo, ("OD", "ESP.", "COMPR.")),
    "pipe": (peso_pipe, ("OD", "ESP.", "COMPR.")),
    "chapa_retangular": (peso_chapa_retangular, ("ESP.", "LARGURA", "COMPR.")),
    "anel": (peso_anel, ("OD", "ID", "ESP.")),
    "disco": (peso_disco, ("OD", "ESP.")),
    "tampo_2_1": (peso_tampo_2_1, ("OD DISCO", "ESP.")),
}


def peso_liquido_geom(familia, dims):
    """Calcula o peso líquido (kgf, 1 peça) de um material geometrizável a partir das
    dimensões do seed. Devolve None se a família não é geometrizável ou faltam dimensões."""
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
    return func(*args, qtd=1)
