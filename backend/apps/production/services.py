"""Serviços de Ordem de Fabricação (H2.1)."""
import math

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from datetime import date

from apps.production.models import (
    OrdemFabricacao, OFItem, OFMaterial, OFOperation, ProductionEntry,
    ActualRate, ProductionObservation,
    STATUS_ABERTA, STATUS_LIBERADA, STATUS_EM_PRODUCAO,
    STATUS_CONCLUIDA, STATUS_CANCELADA,
)
from apps.quotations.models import Quotation
from apps.audit.services import latest_snapshot_for, log_access


def next_of_number() -> str:
    """Gera OF-{ANO}-{SEQ:03d} sequencial no schema do tenant."""
    ano = date.today().year
    prefixo = f"OF-{ano}-"
    ultimo = (OrdemFabricacao.objects.filter(number__startswith=prefixo)
              .order_by("-number").values_list("number", flat=True).first())
    seq = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"{prefixo}{seq:03d}"


def _assert_convertible(quotation):
    """Verifica pré-condições para converter cotação em OF. Retorna o snapshot."""
    snapshot = latest_snapshot_for(quotation)
    if snapshot is None:
        raise ValidationError("Cotação sem CalculationSnapshot — execute o cálculo antes de converter.")

    # Requer aprovação técnica ativa com hash correspondente ao snapshot atual
    approval = quotation.technical_approvals.filter(
        revoked_at__isnull=True,
        calculation_snapshot_hash=snapshot.snapshot_hash,
    ).first()
    if approval is None:
        raise ValidationError(
            "Cotação não possui aprovação técnica ativa para o snapshot atual. "
            "Aprove o cálculo antes de converter em OF."
        )

    # Bloqueia se já existe OF não-cancelada para esta cotação
    existing = quotation.ordens_fabricacao.exclude(status=STATUS_CANCELADA).first()
    if existing is not None:
        raise ValidationError(
            f"Já existe uma Ordem de Fabricação ativa ({existing.number}) para esta cotação."
        )

    return snapshot


@transaction.atomic
def convert_quotation_to_of(quotation, created_by=None, request=None) -> OrdemFabricacao:
    """Converte uma cotação aprovada em Ordem de Fabricação (deep-copy da EAP)."""
    # Lock the quotation row to serialize concurrent converts (defeats the TOCTOU
    # race on the approval / duplicate-OF guard); the partial unique constraint on
    # OrdemFabricacao is the DB-level backstop.
    quotation = Quotation.objects.select_for_update().select_related("customer").get(pk=quotation.pk)
    snapshot = _assert_convertible(quotation)

    of = OrdemFabricacao.objects.create(
        number=next_of_number(),
        quotation=quotation,
        quotation_number=quotation.number,
        quotation_revision=quotation.revision,
        calculation_snapshot=snapshot,
        snapshot_hash=snapshot.snapshot_hash,
        customer_name=quotation.customer.company_name,
        title=quotation.title,
        scope=quotation.scope,
        status=STATUS_ABERTA,
        custo_material=quotation.custo_material,
        custo_mo=quotation.custo_mo,
        custo_total=quotation.custo_total,
        preco_com_impostos=quotation.preco_com_impostos,
        peso_bruto_kg=quotation.peso_bruto_kg,
        peso_liquido_kg=quotation.peso_liquido_kg,
        created_by=created_by,
    )

    # Deep-copy EAP rows
    for i, item in enumerate(quotation.itens.prefetch_related("materiais", "operacoes").all()):
        of_item = OFItem.objects.create(
            ordem=of,
            codigo_item=item.codigo_item,
            descricao=item.descricao,
            custo_material=item.custo_material,
            custo_mo=item.custo_mo,
            sort_order=item.sort_order,
            source_item_id=item.pk,
        )
        for mp in item.materiais.all():
            OFMaterial.objects.create(
                item=of_item,
                codigo_mp=mp.codigo_mp,
                descricao=mp.descricao,
                material=mp.material,
                forma=mp.forma,
                peso_bruto_kg=mp.peso_bruto_kg,
                peso_liquido_kg=mp.peso_liquido_kg,
                preco_kgf=mp.preco_kgf,
                custo=mp.custo,
            )
        for seq, op in enumerate(item.operacoes.all()):
            OFOperation.objects.create(
                item=of_item,
                codigo_op=op.codigo_op,
                descricao=op.descricao,
                metodo=op.metodo,
                custo=op.custo,
                aplicavel=op.aplicavel,
                sequence=seq,
            )

    if request is not None:
        log_access(request, "convert", of, {
            "quotation_id": quotation.pk,
            "quotation_number": quotation.number,
            "snapshot_hash": snapshot.snapshot_hash,
        })

    return of


# Allowed status transitions: {from_status: [allowed_to_statuses]}
ALLOWED_TRANSITIONS = {
    STATUS_ABERTA: [STATUS_LIBERADA, STATUS_CANCELADA],
    STATUS_LIBERADA: [STATUS_EM_PRODUCAO, STATUS_CANCELADA],
    STATUS_EM_PRODUCAO: [STATUS_CONCLUIDA, STATUS_CANCELADA],
    STATUS_CONCLUIDA: [],
    STATUS_CANCELADA: [],
}


@transaction.atomic
def transition(of: OrdemFabricacao, new_status: str, by=None, request=None) -> OrdemFabricacao:
    """Transiciona uma OF para um novo status, validando a transição."""
    old_status = of.status
    allowed = ALLOWED_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise ValidationError(
            f"Transição inválida: {old_status} → {new_status}. "
            f"Permitidas: {allowed or 'nenhuma'}."
        )

    of.status = new_status
    now = timezone.now()

    if new_status == STATUS_LIBERADA:
        of.released_at = now
        of.released_by = by
    elif new_status == STATUS_EM_PRODUCAO:
        of.started_at = now
        of.started_by = by
    elif new_status == STATUS_CONCLUIDA:
        of.completed_at = now
        of.completed_by = by
    elif new_status == STATUS_CANCELADA:
        of.cancelled_at = now
        of.cancelled_by = by

    of.save()

    if new_status == STATUS_CONCLUIDA:
        _close_out_observations(of)

    if request is not None:
        log_access(request, "transition", of, {"transition": f"{old_status}->{new_status}"})

    return of


def liberar(of: OrdemFabricacao, by=None, request=None) -> OrdemFabricacao:
    return transition(of, STATUS_LIBERADA, by=by, request=request)


def iniciar_producao(of: OrdemFabricacao, by=None, request=None) -> OrdemFabricacao:
    return transition(of, STATUS_EM_PRODUCAO, by=by, request=request)


def concluir(of: OrdemFabricacao, by=None, request=None) -> OrdemFabricacao:
    return transition(of, STATUS_CONCLUIDA, by=by, request=request)


def cancelar(of: OrdemFabricacao, by=None, request=None) -> OrdemFabricacao:
    return transition(of, STATUS_CANCELADA, by=by, request=request)


def _close_out_observations(of):
    """No fechamento: grava observação imutável e atualiza ActualRate (R$/h) p/ cada op apontada."""
    from decimal import Decimal
    ops = OFOperation.objects.filter(item__ordem=of).prefetch_related("entries")
    for op in ops:
        if op.custo <= 0:
            continue
        actual_hh = op.actual_hh
        if not actual_hh or actual_hh <= 0:
            continue  # leniente: sem apontamento / 0 horas -> sem observação (evita div/0)
        observed_rate = (Decimal(op.custo) / Decimal(actual_hh)).quantize(Decimal("0.01"))
        ProductionObservation.objects.create(
            operacao=op.codigo_op, ordem=of, of_operation=op,
            estimated_custo=op.custo, actual_hh=actual_hh, observed_rate=observed_rate,
        )
        _update_actual_rate(op.codigo_op, observed_rate)


def log_production_entry(of_operation, operator, hours_hh, hours_hm=0,
                         entry_date=None, notes="", request=None):
    """Registra apontamento de tempo numa operação de OF liberada/em produção."""
    from datetime import date as _date
    status = of_operation.item.ordem.status
    if status not in (STATUS_LIBERADA, STATUS_EM_PRODUCAO):
        raise ValidationError(
            f"Apontamento só é permitido em OF liberada ou em produção (status atual: {status})."
        )
    if hours_hh is not None and float(hours_hh) < 0:
        raise ValidationError("Horas não podem ser negativas.")
    entry = ProductionEntry.objects.create(
        of_operation=of_operation,
        operator=operator,
        hours_hh=hours_hh,
        hours_hm=hours_hm or 0,
        entry_date=entry_date or _date.today(),
        notes=notes or "",
    )
    if request is not None:
        log_access(request, "appoint", entry, {
            "of_id": of_operation.item.ordem_id,
            "of_operation_id": of_operation.pk,
            "hours_hh": str(hours_hh),
        })
    return entry


def _update_actual_rate(operacao: str, observed_rate):
    """Upsert online (Welford) do agregado ActualRate (R$/h) de uma operação. Requer transação."""
    from decimal import Decimal
    ar = ActualRate.objects.select_for_update().filter(operacao=operacao).first()
    if ar is None:
        ar = ActualRate(operacao=operacao)
    r = float(observed_rate)
    n = ar.sample_count + 1
    mean = float(ar.mean_rate)
    m2 = float(ar.m2)
    delta = r - mean
    mean += delta / n
    m2 += delta * (r - mean)
    variance = m2 / n if n >= 1 else 0.0
    stddev = math.sqrt(variance) if variance > 0 else 0.0
    cv = (stddev / mean) if (mean > 0 and n >= 2) else 0.0
    cv = min(max(cv, 0.0), 1.0)
    confidence = (1 - cv) * min(n / 20.0, 1.0)
    ar.sample_count = n
    ar.mean_rate = Decimal(str(round(mean, 2)))
    ar.m2 = Decimal(str(round(m2, 6)))
    ar.confidence = Decimal(str(round(confidence, 4)))
    ar.save()
    return ar
