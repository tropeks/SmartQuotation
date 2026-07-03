"""Validação FINANCEIRA da MATÉRIA-PRIMA (MP) do OF-3683 vs a âncora REAL (Wellington).

OF-3683 é o permutador de calor ELEKEIROZ-CAMAÇARI (TAG E-51303, desenho 17.263-00-1
Rev.2, casco-tubo, inox A-240 TP316L + A-516 Gr.60/70 + A-105, ~8.400 kg) — um
equipamento CUSTOM, sem designação TEMA padrão de catálogo (ao contrário de BEU/BEM).

Via de engine: pricing_engine.permutador_quote.quote_completo(designacao, cost_chain).
"OF3683" NÃO é uma designação TEMA real — é apenas a chave usada para localizar os
seeds pricing_engine/seeds/of3683_materiais.json / of3683_operacoes.json (mesmo
mecanismo de lookup de BEU/BEM, reaproveitado para este job avulso).

Seed de materiais: transcrito item a item das páginas 1-2 do manuscrito
(uploads/render/p3683_p1.png, p3683_p2.png — MATÉRIA-PRIMA; DES 17.263-00-1, 01-2,
02-2, 03-3, 04-2, 05-2, 06-4, 07-4, 08-3). Cada item tem preço (R$) REAL do
orçamento; o price_kgf é o mesmo que está escrito no manuscrito para os lotes de
chapa/tubo (ex.: 46,00 R$/kg para chapa fina 316L, 12,00 para A-516 GR60, 10,00 para
A-36); para os itens de forjado grosso (espelhos, disco casco/DES 03-3, DES 08-3)
sem rate legível, o peso foi derivado por GEOMETRIA (disco/anel × densidade de
norma) e o price_kgf calculado por valor/peso (documentado em "obs" por item no
seed). Itens de fixação/conexões (estojos, porcas, luvas, plugues, flanges,
juntas, placa de identificação) são "familia": "catalogo" — custo = preço direto do
orçamento, sem depender de peso (mesma convenção do BEU/BEM para hardware).

O manuscrito (p3683_p2.png) já traz um TOTAL somado a mão de R$ 481.528,00 — idêntico
à âncora registrada em tests/golden_anchors.json. A soma dos 54 itens transcritos
fecha em R$ 481.521,00 (delta de R$ 7,00 sobre ~meio milhão — 0,0015%, ruído de
arredondamento de 1-2 dígitos manuscritos), o que dá confiança na fidelidade da
transcrição.

Seed de operações (of3683_operacoes.json) foi completado nesta task: transcrição das
páginas 3-8 do manuscrito (uploads/render/p3683_p3.png..p3683_p8.png — operações de
usinagem/solda/inspeção/exame LP-RX-phased array/transporte). O próprio manuscrito
bundla TODAS essas linhas num único bloco "MO" (boxed R$ 213.500,00 na página 8,
checagem intermediária 195.560,00 [pág. 3-7] + 17.940,00 [pág. 8] = 213.500,00); por
isso as 205 linhas transcritas entram como tipo="mao_obra", secao="fabricacao" — mesma
convenção do gabarito original, não a separação mão_obra/serviço do BEU/BEM (que é uma
classificação de PLANILHA, não deste manuscrito). Os 9 itens lump-sum do RESUMO da
página 8 que NÃO têm detalhamento em operações (projeto térmico, projeto mecânico,
desenho, PIT, PS, ferramentas, expandidores, data book, consumível de soldagem) entram
como tipo="servico", secao="finalizacao".

Sem cost_chain (quote_completo(..., cost_chain=None)) e sem params, o motor usa
preco_gabarito direto e eff=1,0 para toda operação — custo_mao_obra e custo_servicos
reproduzem a soma dos valores transcritos exatamente, sem depender de horas/rate/driver
(não usados nesta validação, apenas preco_gabarito). Resultado: MO motor R$ 212.310,00
vs âncora R$ 213.500,00 (delta -0,56%); custo_total motor R$ 734.612,13 vs âncora
R$ 733.510,00 (delta +0,15%) — ambos VERDES, bem dentro da banda ideal (<=5%).

Gate beta do PE: |delta| <= 10% (hard-fail), <= 5% (ideal).
"""
import json
import pathlib

import pytest

from pricing_engine.permutador_quote import quote_completo

_ANCHORS = json.loads((pathlib.Path(__file__).parent / "golden_anchors.json").read_text())

GATE_HARD_PCT = 10.0
GATE_IDEAL_PCT = 5.0


def _delta_pct(motor, real):
    return (motor / real - 1.0) * 100.0


def _cot_of3683():
    return quote_completo("of3683", cost_chain=None)


def test_of3683_seed_carrega_54_itens():
    """Guarda de integridade: os seeds transcritos não podem encolher/crescer silenciosamente."""
    cot = _cot_of3683()
    assert cot["n_materiais"] == 54
    assert cot["n_operacoes"] == 214


def test_of3683_MP_dentro_do_gate():
    """MP do motor (Σ peso_bruto × price_kgf dos 54 itens transcritos) vs a âncora real
    R$ 481.528,00. Como o seed usa peso e price_kgf DERIVADOS do próprio manuscrito
    (não recalculados por um modelo geométrico independente — este é um job avulso,
    sem gabarito TEMA calibrado como BEU/BEM), o resultado reproduz a soma do
    orçamento real quase exatamente (delta ~0,0016%)."""
    real = _ANCHORS["OF-3683"]["subtotais"]["MP"]
    mp = _cot_of3683()["custo_material"]
    delta = _delta_pct(mp, real)
    assert abs(delta) <= GATE_HARD_PCT, (
        f"OF-3683 MP fora do gate hard-fail: motor={mp:,.2f} real={real:,.2f} delta={delta:+.2f}%")


def test_of3683_MP_dentro_da_banda_ideal():
    """Banda ideal (<=5%) — mais apertada que o gate hard-fail acima."""
    real = _ANCHORS["OF-3683"]["subtotais"]["MP"]
    mp = _cot_of3683()["custo_material"]
    assert abs(_delta_pct(mp, real)) <= GATE_IDEAL_PCT


# ---- MO (mão-de-obra, páginas 3-8) vs a âncora real R$ 213.500,00 ----

def test_of3683_MO_dentro_do_gate():
    """MO do motor (Σ preco_gabarito das 205 linhas transcritas de of3683_operacoes.json,
    tipo=mao_obra) vs a âncora real R$ 213.500,00. Sem cost_chain/params, eff=1,0 para toda
    operação — custo_mao_obra reproduz a soma dos valores manuscritos quase diretamente
    (delta ~ -0,56%, ruído de leitura de ~205 linhas manuscritas densas)."""
    real = _ANCHORS["OF-3683"]["subtotais"]["MO"]
    mo = _cot_of3683()["custo_mao_obra"]
    delta = _delta_pct(mo, real)
    assert abs(delta) <= GATE_HARD_PCT, (
        f"OF-3683 MO fora do gate hard-fail: motor={mo:,.2f} real={real:,.2f} delta={delta:+.2f}%")


def test_of3683_MO_dentro_da_banda_ideal():
    """Banda ideal (<=5%) — mais apertada que o gate hard-fail acima."""
    real = _ANCHORS["OF-3683"]["subtotais"]["MO"]
    mo = _cot_of3683()["custo_mao_obra"]
    assert abs(_delta_pct(mo, real)) <= GATE_IDEAL_PCT


# ---- TOTAL (MP + MO + itens lump-sum do resumo) vs a âncora real R$ 733.510,00 ----

def test_of3683_TOTAL_dentro_do_gate():
    """Validação financeira principal: custo_total do motor (MP + MO + serviços lump-sum
    do resumo — projeto térmico/mecânico, desenho, PIT, PS, ferramentas, expandidores,
    data book, consumível) vs a âncora real R$ 733.510,00 (delta ~ +0,15%)."""
    real = _ANCHORS["OF-3683"]["custo_total"]
    total = _cot_of3683()["custo_total"]
    delta = _delta_pct(total, real)
    assert abs(delta) <= GATE_HARD_PCT, (
        f"OF-3683 TOTAL fora do gate hard-fail: motor={total:,.2f} real={real:,.2f} delta={delta:+.2f}%")


def test_of3683_TOTAL_dentro_da_banda_ideal():
    """Banda ideal (<=5%) — mais apertada que o gate hard-fail acima."""
    real = _ANCHORS["OF-3683"]["custo_total"]
    total = _cot_of3683()["custo_total"]
    assert abs(_delta_pct(total, real)) <= GATE_IDEAL_PCT
