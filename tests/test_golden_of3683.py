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

Seed de operações (of3683_operacoes.json) é uma lista VAZIA de propósito: a MO real
do job (âncora R$ 213.500) está nas páginas 3-8 do manuscrito (operações de usinagem/
solda/inspeção), que NÃO foram transcritas — escopo desta task é só a MP. Isso é
seguro porque quote_completo() separa custo_material de custo_mao_obra/custo_servicos;
com "operacoes": [] os dois últimos ficam 0,0 e não contaminam a validação de MP.

Gate beta do PE: |delta| <= 10% (hard-fail), <= 5% (ideal). Resultado: delta ≈ -0,0016%
— VERDE, bem dentro da banda ideal.
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
    """Guarda de integridade: o seed transcrito não pode encolher/crescer silenciosamente."""
    cot = _cot_of3683()
    assert cot["n_materiais"] == 54
    assert cot["n_operacoes"] == 0


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
