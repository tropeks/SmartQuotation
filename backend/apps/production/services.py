"""Serviços de Ordem de Fabricação (H2.1)."""
import math
import re

from django.core.exceptions import ValidationError
from django.db import connection
from django.db import transaction
from django.utils import timezone
from datetime import date

from apps.production.models import (
    OrdemFabricacao, OFItem, OFMaterial, OFOperation, ProductionEntry,
    ActualRate, ProductionObservation, InspectionPlan, InspectionItem,
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


def is_convertible(quotation) -> bool:
    """True sse a conversão em OF passaria — MESMA regra do POST.

    Reusa `_assert_convertible` (a checagem real feita em `convert_quotation_to_of`)
    para o front não divergir da trava do backend. Retorna False em vez de levantar.
    """
    try:
        _assert_convertible(quotation)
    except ValidationError:
        return False
    return True


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
                horas_hh=op.horas_hh,
                horas_hm=op.horas_hm,
                taxa_hora=op.taxa_hora,
                taxa_hora_hm=op.taxa_hora_hm,
                custo_direto=op.custo_direto,
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

    if new_status == STATUS_LIBERADA:
        _schedule_protheus_export(of)
        # A SPEC pede export no evento de "conversão"; seguimos a convenção já
        # existente (disparo na liberação) para consistência com sap_b1/protheus.
        # Se o dono do produto quiser mover para a conversão (STATUS_ABERTA), é
        # um ajuste de 1 linha aqui.
        from apps.integrations.routing import get_active_erp

        active_erp = get_active_erp()
        if active_erp == "nomus":
            _schedule_nomus_export(of)
        elif active_erp == "sap_b1":
            _schedule_sap_b1_export(of)

    if new_status == STATUS_CONCLUIDA:
        _close_out_observations(of)
        _schedule_omie_nfe_issue(of)

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


def _schedule_protheus_export(of):
    from apps.integrations.protheus import services as protheus_services

    run = protheus_services.maybe_enqueue_work_order_export(of, trigger="release")
    if run is None:
        return None
    schema_name = connection.schema_name
    transaction.on_commit(
        lambda: protheus_services.enqueue_sync_run_async(run, schema_name=schema_name)
    )
    return run


def _schedule_sap_b1_export(of):
    try:
        from apps.integrations.sap_b1 import services as sap_b1_services
    except ImportError:
        return None, None

    schema_name = connection.schema_name
    so_run = sap_b1_services.maybe_enqueue_sales_order_sync(of, trigger="release")
    if so_run is not None:
        transaction.on_commit(
            lambda: sap_b1_services.enqueue_sync_run_async(so_run, schema_name=schema_name)
        )

    bom_run = sap_b1_services.maybe_enqueue_bom_sync(of, trigger="release")
    if bom_run is not None:
        transaction.on_commit(
            lambda: sap_b1_services.enqueue_sync_run_async(bom_run, schema_name=schema_name)
        )

    return so_run, bom_run


def _schedule_nomus_export(of, trigger="release"):
    from apps.integrations.nomus import services as nomus_services

    run = nomus_services.maybe_enqueue_export(of, trigger=trigger)
    if run is None:
        return None
    schema_name = connection.schema_name
    transaction.on_commit(
        lambda: nomus_services.enqueue_sync_run_async(run, schema_name=schema_name)
    )
    return run


def reexport_nomus(of, by=None, request=None):
    """Reexport manual da OF para o Nomus (botão da UI — task 6)."""
    run = _schedule_nomus_export(of, trigger="manual")
    if request is not None:
        log_access(request, "nomus_reexport", of, {
            "of_number": of.number,
            "run_id": getattr(run, "pk", None),
        })
    return run


def _schedule_omie_nfe_issue(of):
    """Agenda emissão de NF-e via Omie após commit quando houver fila para gerar."""
    try:
        from apps.integrations.omie import services as omie_services
    except ImportError:
        return None

    maybe_enqueue_nfe_issue = getattr(omie_services, "maybe_enqueue_nfe_issue", None)
    enqueue_invoice_run_async = getattr(omie_services, "enqueue_invoice_run_async", None)
    if maybe_enqueue_nfe_issue is None or enqueue_invoice_run_async is None:
        return None

    run = maybe_enqueue_nfe_issue(of, trigger="of_completed")
    if run is None:
        return None

    schema_name = connection.schema_name
    transaction.on_commit(
        lambda: enqueue_invoice_run_async(run, schema_name=schema_name)
    )
    return run


def _close_out_observations(of):
    """No fechamento: grava observação imutável e atualiza ActualRate (R$/h) p/ cada op apontada."""
    from decimal import Decimal
    ops = OFOperation.objects.filter(item__ordem=of).prefetch_related("entries")
    for op in ops:
        if op.custo <= 0:
            continue
        actual_hh = sum((e.hours_hh for e in op.entries.all()), Decimal("0"))
        if actual_hh <= 0:
            continue  # leniente: sem apontamento / 0 horas -> sem observação (evita div/0)
        observed_rate = (Decimal(op.custo) / Decimal(actual_hh)).quantize(Decimal("0.01"))
        # SQ-COST-3: snapshot de horas orçadas (ProcessParameter) para separar erro de horas
        # (estimativa física) de erro de R$/h (Rate) — ver docs/specs/sq-cost-1... Seção 6.
        # estimated_hh=0 é legítimo (operação de valor fixo, wbs.custo_fixo) -> delta fica None.
        estimated_hh = Decimal(op.horas_hh)
        delta_horas_pct = None
        if estimated_hh > 0:
            delta_horas_pct = (
                (Decimal(actual_hh) - estimated_hh) / estimated_hh * Decimal("100")
            ).quantize(Decimal("0.01"))
        ProductionObservation.objects.create(
            operacao=op.codigo_op, ordem=of, of_operation=op,
            estimated_custo=op.custo, actual_hh=actual_hh, observed_rate=observed_rate,
            estimated_hh=estimated_hh, delta_horas_pct=delta_horas_pct,
        )
        _update_actual_rate(op.codigo_op, observed_rate)


def log_production_entry(of_operation, operator, hours_hh, hours_hm=0,
                         entry_date=None, notes="", request=None):
    """Registra apontamento de tempo numa operação de OF liberada/em produção."""
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation
    status = of_operation.item.ordem.status
    if status not in (STATUS_LIBERADA, STATUS_EM_PRODUCAO):
        raise ValidationError(
            f"Apontamento só é permitido em OF liberada ou em produção (status atual: {status})."
        )
    try:
        hh = Decimal(str(hours_hh)) if hours_hh is not None else Decimal("0")
        hm = Decimal(str(hours_hm)) if hours_hm is not None else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Horas inválidas.")
    if hh < 0 or hm < 0:
        raise ValidationError("Horas não podem ser negativas.")
    if hh > 24:
        raise ValidationError("Horas não podem exceder 24 por apontamento.")
    if hm > 24:
        raise ValidationError("Horas de máquina não podem exceder 24 por apontamento.")
    if isinstance(entry_date, str) and entry_date:
        try:
            resolved_entry_date = _date.fromisoformat(entry_date)
        except ValueError:
            raise ValidationError("Data inválida.")
    else:
        resolved_entry_date = entry_date if isinstance(entry_date, _date) else _date.today()
    if resolved_entry_date > _date.today():
        raise ValidationError("Data do apontamento não pode ser futura.")
    entry = ProductionEntry.objects.create(
        of_operation=of_operation,
        operator=operator,
        hours_hh=hh,
        hours_hm=hm,
        entry_date=resolved_entry_date,
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
    ActualRate.objects.get_or_create(operacao=operacao)  # atômico: cria a linha se não existir
    ar = ActualRate.objects.select_for_update().get(operacao=operacao)  # trava p/ o update
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
    ar.mean_rate = Decimal(str(round(mean, 6)))
    ar.m2 = Decimal(str(round(m2, 6)))
    ar.confidence = Decimal(str(round(confidence, 4)))
    ar.save()
    return ar


def _inspection_type_for(op: OFOperation) -> str:
    text = f"{op.codigo_op} {op.descricao}".upper()
    tokens = set(re.findall(r"[A-Z0-9]+", text))
    if "HIDRO" in text or "TESTE" in text:
        return "hidrostatico"
    if tokens & {"LP", "RT", "RX", "UT", "PM"} or "EXAME" in tokens:
        return "ndt"
    if "INSPEC" in text:
        return "visual"
    if any(token in text for token in ("FURAR", "USINAR", "CORTAR", "RECORTAR", "RASGO", "ALARGAR")):
        return "dimensional"
    if any(token in text for token in ("PLANO", "PIT", "PS", "DOC")):
        return "documental"
    return "processo"


@transaction.atomic
def generate_inspection_plan(of: OrdemFabricacao, generated_by=None, request=None) -> InspectionPlan:
    """Gera ITP básico a partir do roteiro congelado da OF, sem duplicar em chamadas repetidas."""
    of = OrdemFabricacao.objects.select_for_update().get(pk=of.pk)
    if of.status == STATUS_CANCELADA:
        raise ValidationError("Não é possível gerar ITP para OF cancelada.")

    existing = getattr(of, "inspection_plan", None)
    if existing is not None:
        return existing

    ops = list(
        OFOperation.objects.filter(item__ordem=of, aplicavel=True)
        .select_related("item")
        .order_by("item__sort_order", "sequence", "id")
    )
    if not ops:
        raise ValidationError("Não há operações aplicáveis para gerar ITP.")
    plan = InspectionPlan.objects.create(
        ordem=of,
        source_snapshot_hash=of.snapshot_hash,
        source_operations_count=len(ops),
        generated_by=generated_by,
    )
    for seq, op in enumerate(ops, start=1):
        InspectionItem.objects.create(
            plan=plan,
            of_operation=op,
            sequence=seq,
            codigo_item=op.item.codigo_item,
            item_descricao=op.item.descricao,
            codigo_op=op.codigo_op,
            descricao=op.descricao,
            metodo=op.metodo,
            inspection_type=_inspection_type_for(op),
            criterio="Conforme roteiro, desenho aprovado e requisitos do pedido.",
        )

    if request is not None:
        log_access(request, "itp_generate", plan, {
            "of_id": of.pk,
            "of_number": of.number,
            "items": len(ops),
            "snapshot_hash": of.snapshot_hash,
        })
    return plan


@transaction.atomic
def accept_inspection_item(item: InspectionItem, accepted_by, notes="", request=None) -> InspectionItem:
    """Registra aceite de um item do ITP com responsável e data."""
    item = (
        InspectionItem.objects.select_for_update()
        .select_related("plan__ordem")
        .get(pk=item.pk)
    )
    plan = InspectionPlan.objects.select_for_update().get(pk=item.plan_id)
    if item.plan.ordem.status == STATUS_CANCELADA:
        raise ValidationError("Não é possível aceitar ITP de OF cancelada.")
    if item.status == InspectionItem.STATUS_ACCEPTED:
        raise ValidationError("Item de ITP já aceito.")

    item.status = InspectionItem.STATUS_ACCEPTED
    item.accepted_by = accepted_by
    item.accepted_at = timezone.now()
    item.notes = notes or ""
    item.save(update_fields=["status", "accepted_by", "accepted_at", "notes"])

    pending = plan.items.exclude(status=InspectionItem.STATUS_ACCEPTED).exists()
    if not pending:
        plan.status = InspectionPlan.STATUS_COMPLETED
        plan.completed_at = timezone.now()
        plan.save(update_fields=["status", "completed_at", "updated_at"])

    if request is not None:
        log_access(request, "itp_accept", item, {
            "of_id": item.plan.ordem_id,
            "inspection_plan_id": item.plan_id,
            "codigo_op": item.codigo_op,
        })
    return item
