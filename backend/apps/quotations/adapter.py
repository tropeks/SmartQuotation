"""
Adapter Django <-> pricing_engine (ÚNICO ponto de acoplamento).

- to_feixe_inputs(quotation): dict de inputs (data sheet) -> FeixeInputs.
- recompute(quotation): chama pricing_engine.quote_feixe e persiste a EAP
  (QuotationItem/ItemMaterial/ItemOperation) + totais, como SNAPSHOT.

pricing_engine permanece PURO (zero import Django). float -> Decimal na fronteira.
"""
from dataclasses import fields
from decimal import Decimal
from django.utils import timezone

from pricing_engine.feixe_inputs import FeixeInputs, caso_136_tubos
from pricing_engine.feixe_quote import quote_feixe
from apps.quotations.models import QuotationItem, ItemMaterial, ItemOperation

_FIELD_NAMES = {f.name for f in fields(FeixeInputs)}
ITENS_ENG_FER = {  # itens que o quote_feixe agrega como escalares
    "ENG-01": "Engenharia", "FER-01": "Ferramentas / Consumíveis",
}


def D(x) -> Decimal:
    return Decimal(str(round(float(x), 6)))


def default_inputs() -> dict:
    """Inputs default (caso 136 tubos) — ponto de partida do data sheet."""
    base = caso_136_tubos()
    return {f.name: getattr(base, f.name) for f in fields(FeixeInputs)}


def to_feixe_inputs(quotation) -> FeixeInputs:
    """Monta FeixeInputs do JSON do data sheet, preenchendo defaults ausentes."""
    data = {k: v for k, v in (quotation.inputs or {}).items() if k in _FIELD_NAMES}
    merged = {**default_inputs(), **data}
    return FeixeInputs(**merged)


def recompute(quotation) -> None:
    """Recomputa a cotação via pricing_engine e persiste a EAP (snapshot)."""
    inp = to_feixe_inputs(quotation)
    cot = quote_feixe(inp, fator_preco=float(quotation.fator_preco),
                      impostos_pct=float(quotation.impostos_pct))

    # limpa EAP anterior (deep-copy/snapshot, não referência viva)
    quotation.itens.all().delete()

    custo_material = Decimal("0")
    custo_mo = Decimal("0")
    peso_bruto = Decimal("0")
    peso_liquido = Decimal("0")
    order = 0

    for it in cot.itens:
        qi = QuotationItem.objects.create(
            quotation=quotation, codigo_item=it.codigo_item, descricao=it.descricao,
            custo_material=D(it.custo_material), custo_mo=D(it.custo_mo), sort_order=order)
        order += 1
        for mp in it.materias_primas:
            ItemMaterial.objects.create(
                item=qi, codigo_mp=mp.codigo_mp, descricao=mp.descricao,
                material=mp.material, forma=mp.forma,
                peso_bruto_kg=D(mp.peso_kg), peso_liquido_kg=D(mp.peso_liquido),
                preco_kgf=D(mp.preco_kgf), custo=D(mp.custo))
            peso_bruto += D(mp.peso_kg)
            peso_liquido += D(mp.peso_liquido)
        for op in it.operacoes:
            if op.custo:
                ItemOperation.objects.create(
                    item=qi, codigo_op=op.codigo_op, descricao=op.descricao,
                    metodo=op.metodo, custo=D(op.custo), aplicavel=op.aplicavel)
        custo_material += D(it.custo_material)
        custo_mo += D(it.custo_mo)

    # engenharia + ferramentas como itens da EAP (completude)
    for code, desc in ITENS_ENG_FER.items():
        valor = cot.custo_engenharia if code == "ENG-01" else cot.custo_ferramentas
        if valor:
            QuotationItem.objects.create(
                quotation=quotation, codigo_item=code, descricao=desc,
                custo_material=Decimal("0"), custo_mo=D(valor), sort_order=order)
            order += 1
            custo_mo += D(valor)

    # totais (snapshot do roll-up + formação de preço)
    quotation.custo_material = custo_material
    quotation.custo_mo = custo_mo
    quotation.custo_total = D(cot.custo_total)
    quotation.preco_sem_impostos = D(cot.preco_sem_impostos)
    quotation.preco_com_impostos = D(cot.preco_com_impostos)
    quotation.peso_bruto_kg = peso_bruto
    quotation.peso_liquido_kg = peso_liquido
    quotation.computed_at = timezone.now()
    quotation.save()
