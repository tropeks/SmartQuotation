"""
Adapter Django <-> pricing_engine (ÚNICO ponto de acoplamento).

- to_feixe_inputs(quotation): dict de inputs (data sheet) -> FeixeInputs.
- recompute(quotation): chama pricing_engine.quote_feixe e persiste a EAP
  (QuotationItem/ItemMaterial/ItemOperation) + totais, como SNAPSHOT.

pricing_engine permanece PURO (zero import Django). float -> Decimal na fronteira.
"""
from dataclasses import fields
from decimal import Decimal
from django.db import models
from django.utils import timezone

from pricing_engine.feixe_inputs import FeixeInputs, caso_136_tubos
from pricing_engine.feixe_quote import quote_feixe
from pricing_engine.rates import TenantCostChain, op_key
from apps.quotations.models import QuotationItem, ItemMaterial, ItemOperation

_FIELD_NAMES = {f.name for f in fields(FeixeInputs)}
ITENS_ENG_FER = {  # itens que o quote_feixe agrega como escalares
    "ENG-01": "Engenharia", "FER-01": "Ferramentas / Consumíveis",
}


def D(x) -> Decimal:
    return Decimal(str(round(float(x), 6)))


def _to_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# Parte TEMA → forma de material (p/ lookup de preço no tenant cost chain).
_FORMA_POR_PARTE = {
    "shell": "chapa", "tubesheet": "chapa", "baffle": "chapa",
    "front_head": "chapa", "rear_head": "chapa",
    "tube_bundle": "tubo", "nozzle": "tubo", "flange": "forjado", "tie_rod": "barra",
}


def default_inputs() -> dict:
    """Inputs default (caso 136 tubos) — ponto de partida do data sheet."""
    base = caso_136_tubos()
    return {f.name: getattr(base, f.name) for f in fields(FeixeInputs)}


def to_feixe_inputs(quotation) -> FeixeInputs:
    """Monta FeixeInputs do JSON do data sheet, preenchendo defaults ausentes."""
    data = {k: v for k, v in (quotation.inputs or {}).items() if k in _FIELD_NAMES}
    merged = {**default_inputs(), **data}
    return FeixeInputs(**merged)


def build_cost_chain(quotation) -> TenantCostChain:
    """Monta a CADEIA DE CUSTOS do tenant a partir do banco (wizard A1-c popula/calibra):
    preços de material (por material×forma), fator de correção de MO, markup e impostos.
    """
    from datetime import date
    chain = TenantCostChain(
        fator_preco=float(quotation.fator_preco),
        impostos_pct=float(quotation.impostos_pct),
    )
    # preços de material vigentes (cifrados) por (sigla, forma)
    try:
        from apps.materials.models import MaterialPrice
        hoje = date.today()
        for mp in MaterialPrice.objects.select_related("material").filter(valid_from__lte=hoje):
            if mp.valid_until and mp.valid_until < hoje:
                continue
            try:
                chain.material_price[(mp.material.sigla.upper(), mp.forma.lower())] = float(mp.preco_brl_kg)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    # fator de correção de MO (knob calibrado pelo back-solve)
    try:
        from apps.engineering_params.models import ProcessParameter, Rate, TenantParamConfig
        hoje = date.today()
        for r in (Rate.objects.filter(valid_from__lte=hoje)
                  .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=hoje))
                  .order_by("valid_from")):
            chain.rate_hh[op_key(r.operacao)] = float(r.rate_hh)
            if r.rate_hm is not None:
                chain.rate_hm[op_key(r.operacao)] = float(r.rate_hm)
        for pp_obj in (ProcessParameter.objects.filter(valid_from__lte=hoje, valor__isnull=False)
                       .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=hoje))
                       .order_by("valid_from")):
            if pp_obj.operacao == "ALARGAR_ESPELHO" and pp_obj.metodo == "cnc":
                continue
            chain.process_params[
                (pp_obj.operacao, pp_obj.metodo, pp_obj.material or None)
            ] = float(pp_obj.valor)
        cfg = TenantParamConfig.get_solo()
        chain.fator_correcao_mo = float(cfg.fator_correcao_mo)
    except Exception:
        pass
    return chain


def recompute(quotation) -> None:
    """Recomputa a cotação e persiste a EAP, RAMIFICANDO por scope:
    - tube_bundle → quote_feixe (motor do feixe) — caminho histórico, intocado.
    - complete    → quote_completo (permutador completo por designação TEMA).
    - parts       → soma das QuotationParts inclusas (custeio de casco/cabeçote via
                    ComponentOperation × ProcessParameter × Rate).
    """
    scope = getattr(quotation, "scope", "tube_bundle")
    if scope == "parts":
        _recompute_parts(quotation)
    elif scope == "complete":
        _recompute_complete(quotation)
    else:
        _recompute_feixe(quotation)
    _apply_avisos(quotation)


def _apply_avisos(quotation) -> None:
    """Roda os validadores de negócio e persiste em Quotation.avisos (não quebra o custeio)."""
    from apps.quotations.validators import validate_metalurgia
    try:
        avisos = list(validate_metalurgia(quotation))
    except Exception:
        avisos = []
    quotation.avisos = avisos
    quotation.save(update_fields=["avisos"])


def _recompute_feixe(quotation) -> None:
    """Recomputa a cotação via pricing_engine (com a cadeia de custos do tenant) e persiste a EAP."""
    inp = to_feixe_inputs(quotation)
    cot = quote_feixe(inp, cost_chain=build_cost_chain(quotation))

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
                    metodo=op.metodo, custo=D(op.custo),
                    horas_hh=D(op.horas_hh), horas_hm=D(op.horas_hm),
                    taxa_hora=D(op.rate_hh), taxa_hora_hm=D(op.rate_hm),
                    custo_direto=(op.horas_hh == 0 and op.horas_hm == 0),
                    aplicavel=op.aplicavel,
                    origem="seed",
                    horas_hh_sugerida=D(op.horas_hh), horas_hm_sugerida=D(op.horas_hm))
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


def _recompute_parts(quotation) -> None:
    """Custeia uma cotação por PARTES avulsas (scope='parts'): cada QuotationPart inclusa
    vira um QuotationItem, com material = massa × preço do tenant e MO derivada do roteiro
    sugerido do ComponentTemplate (ComponentOperation × ProcessParameter × Rate × FC).
    Valores são DEFAULTS sugeridos (origem='template'); o orçamentista sobrescreve no drawer.
    Operação sem ProcessParameter/Rate vigente entra como sugerida-não-custeável (aplicavel=False),
    nunca quebra o custeio."""
    from apps.engineering_params.models import ProcessParameter, Rate, TenantParamConfig

    chain = build_cost_chain(quotation)
    fator_mo = float(TenantParamConfig.get_solo().fator_correcao_mo)

    quotation.itens.all().delete()
    custo_material = Decimal("0")
    custo_mo = Decimal("0")
    peso_bruto = Decimal("0")
    order = 0

    for part in quotation.parts.filter(incluso=True).select_related("template"):
        tmpl = part.template
        qi = QuotationItem.objects.create(
            quotation=quotation,
            codigo_item=(f"{tmpl.tema_part}-{part.tema_letter}".strip("-"))[:30],
            descricao=str(tmpl)[:255], sort_order=order)
        order += 1
        params = part.params or {}
        material = (part.material_sigla or "").strip()

        # material: massa × preço (forma pela parte TEMA)
        massa = _to_float(params.get("massa"))
        forma = _FORMA_POR_PARTE.get(tmpl.tema_part, "chapa")
        preco = chain.material_price.get((material.upper(), forma)) if material else None
        item_mat = Decimal("0")
        if massa and preco:
            item_mat = D(massa * float(preco))
            ItemMaterial.objects.create(
                item=qi, codigo_mp=(material or forma)[:30],
                descricao=f"{tmpl.get_tema_part_display()} — {forma}"[:255],
                material=material[:50], forma=forma,
                peso_bruto_kg=D(massa), peso_liquido_kg=D(massa),
                preco_kgf=D(preco), custo=item_mat)
            peso_bruto += D(massa)

        # MO: roteiro sugerido do template
        item_mo = Decimal("0")
        for co in tmpl.component_operations.all():
            driver_val = 1.0 if co.driver == "fixo" else _to_float(params.get(co.driver))
            pp = ProcessParameter.objects.vigente(co.operacao, co.metodo or "", material or None)
            rate = Rate.objects.vigente(co.operacao)
            if pp is None or pp.valor is None or rate is None:
                ItemOperation.objects.create(
                    item=qi, codigo_op=co.codigo_op[:40], descricao=co.descricao[:255],
                    metodo=co.metodo, custo=Decimal("0"), custo_direto=False, aplicavel=False,
                    origem="template", horas_hh_sugerida=Decimal("0"), horas_hm_sugerida=Decimal("0"))
                continue
            horas_hh = driver_val * float(pp.valor) + float(co.setup_fixo)
            custo_op = D(horas_hh * float(rate.rate_hh) * fator_mo)
            ItemOperation.objects.create(
                item=qi, codigo_op=co.codigo_op[:40], descricao=co.descricao[:255],
                metodo=co.metodo, custo=custo_op, custo_direto=False,
                aplicavel=co.aplicavel_default,
                horas_hh=D(horas_hh), horas_hm=Decimal("0"),
                taxa_hora=D(rate.rate_hh), taxa_hora_hm=D(rate.rate_hm or 0),
                origem="template", horas_hh_sugerida=D(horas_hh), horas_hm_sugerida=Decimal("0"))
            item_mo += custo_op

        qi.custo_material = item_mat
        qi.custo_mo = item_mo
        qi.save(update_fields=["custo_material", "custo_mo"])
        custo_material += item_mat
        custo_mo += item_mo

    custo_total = custo_material + custo_mo
    quotation.custo_material = custo_material
    quotation.custo_mo = custo_mo
    quotation.custo_total = custo_total
    preco_sem = custo_total * quotation.fator_preco
    quotation.preco_sem_impostos = D(preco_sem)
    quotation.preco_com_impostos = D(preco_sem * (1 + quotation.impostos_pct / Decimal("100")))
    quotation.peso_bruto_kg = peso_bruto
    quotation.peso_liquido_kg = peso_bruto
    quotation.computed_at = timezone.now()
    quotation.save()


def _recompute_complete(quotation) -> None:
    """Recomputa um permutador completo (scope='complete') por designação TEMA, reusando o
    motor via tema_templates.estimate_complete e repersistindo a EAP por seção (mesma forma
    de services.create_permutador_quotation). SEGURO: se a designação não é custeável, é
    NO-OP (preserva o snapshot atual em vez de zerar a cotação)."""
    from apps.tema_templates.services import estimate_complete

    desig = (quotation.inputs or {}).get("designacao")
    resultado = estimate_complete(desig) if desig else None
    if not resultado:
        return

    quotation.itens.all().delete()
    for i, (secao, valor) in enumerate(sorted((resultado.get("por_secao") or {}).items())):
        is_material = "material" in secao
        QuotationItem.objects.create(
            quotation=quotation, codigo_item=secao[:30],
            descricao=secao.replace("_", " ").title()[:255],
            custo_material=D(valor) if is_material else Decimal("0"),
            custo_mo=Decimal("0") if is_material else D(valor), sort_order=i)

    custo_mo = float(resultado.get("custo_mao_obra", 0)) + float(resultado.get("custo_servicos", 0))
    quotation.custo_material = D(resultado.get("custo_material") or 0)
    quotation.custo_mo = D(custo_mo)
    quotation.custo_total = D(resultado.get("custo_total") or 0)
    quotation.preco_sem_impostos = D(resultado.get("preco_sem_impostos") or 0)
    quotation.preco_com_impostos = D(resultado.get("preco_com_impostos") or 0)
    quotation.computed_at = timezone.now()
    quotation.save()
