from __future__ import annotations

import logging

from django.db import connection, transaction

from apps.integrations.nomus.client import HttpNomusTransientError, build_nomus_client
from apps.integrations.nomus.fake import MemoryNomusClient
from apps.integrations.nomus.models import NomusExportLog, NomusIntegrationConfig, NomusSyncRun
from apps.production.models import OrdemFabricacao, STATUS_LIBERADA

logger = logging.getLogger(__name__)


class NomusTaskEnqueueError(RuntimeError):
    pass


def get_enabled_config():
    return NomusIntegrationConfig.objects.filter(provider=NomusIntegrationConfig.PROVIDER, enabled=True).first()


def get_config():
    return NomusIntegrationConfig.objects.filter(provider=NomusIntegrationConfig.PROVIDER).order_by("-updated_at").first()


def _serialize_materials(of: OrdemFabricacao):
    materials = []
    items = of.itens.prefetch_related("materiais", "operacoes").order_by("sort_order", "codigo_item", "pk")
    for item in items:
        for material in item.materiais.order_by("codigo_mp", "pk"):
            materials.append({
                "item_code": item.codigo_item,
                "codigo_mp": material.codigo_mp,
                "descricao": material.descricao,
                "material": material.material,
                "forma": material.forma,
                "peso_bruto_kg": str(material.peso_bruto_kg),
                "custo": str(material.custo),
            })
    return materials


def _serialize_routing(of: OrdemFabricacao):
    routing = []
    items = of.itens.prefetch_related("operacoes").order_by("sort_order", "codigo_item", "pk")
    for item in items:
        for operation in item.operacoes.order_by("sequence", "codigo_op", "pk"):
            routing.append({
                "item_code": item.codigo_item,
                "codigo_op": operation.codigo_op,
                "descricao": operation.descricao,
                "metodo": operation.metodo,
                "horas_hh": str(operation.horas_hh),
                "horas_hm": str(operation.horas_hm),
                "taxa_hora": str(operation.taxa_hora),
                "custo": str(operation.custo),
                "sequence": operation.sequence,
            })
    return routing


def serialize_production_order_from_of(of: OrdemFabricacao):
    return {
        "provider": NomusIntegrationConfig.PROVIDER,
        "entity": NomusSyncRun.ENTITY_PRODUCTION_ORDER,
        "order_number": of.number,
        "quotation_number": of.quotation_number,
        "quotation_revision": of.quotation_revision,
        "customer_name": of.customer_name,
        "title": of.title,
        "scope": of.scope,
        "status": of.status,
        "totals": {
            "custo_material": str(of.custo_material),
            "custo_mo": str(of.custo_mo),
            "custo_total": str(of.custo_total),
            "preco_com_impostos": str(of.preco_com_impostos),
        },
        "lista_material": _serialize_materials(of),
        "roteiro": _serialize_routing(of),
        "source_snapshot": {
            "of_id": of.pk,
            "of_number": of.number,
            "snapshot_hash": of.snapshot_hash,
            "status": of.status,
        },
    }


def maybe_enqueue_export(of: OrdemFabricacao, trigger="manual"):
    if of.status != STATUS_LIBERADA:
        return None
    config = get_enabled_config()
    if config is None or not config.enabled:
        return None
    return NomusSyncRun.objects.create(
        direction=NomusSyncRun.DIRECTION_PUSH,
        entity_type=NomusSyncRun.ENTITY_PRODUCTION_ORDER,
        payload=serialize_production_order_from_of(of) | {"trigger": trigger},
    )


def enqueue_sync_run_async(run: NomusSyncRun, schema_name=None):
    schema_name = schema_name or connection.schema_name
    from apps.integrations.nomus.tasks import process_nomus_sync_run

    try:
        process_nomus_sync_run.delay(schema_name=schema_name, run_id=run.pk)
    except Exception as exc:
        logger.exception(
            "Failed to enqueue Nomus sync run",
            extra={"schema_name": schema_name, "run_id": run.pk},
        )
        raise NomusTaskEnqueueError("Failed to enqueue Nomus sync run") from exc
    return True


def _build_client():
    config = get_enabled_config() or get_config()
    if config is None or not config.base_url:
        return MemoryNomusClient()
    return build_nomus_client(base_url=config.base_url, access_key=config.access_key or "")


def _detect_and_flag_of_conflict(run: NomusSyncRun):
    order_number = (run.payload or {}).get("order_number")
    if not order_number:
        return None

    previous_log = (
        NomusExportLog.objects.filter(
            status=NomusExportLog.STATUS_EXPORTED,
            sync_run__entity_type=NomusSyncRun.ENTITY_PRODUCTION_ORDER,
            sync_run__payload__order_number=order_number,
        )
        .exclude(sync_run=run)
        .order_by("-created_at")
        .first()
    )
    if previous_log is None:
        return None

    export_log, _ = NomusExportLog.objects.get_or_create(sync_run=run)
    export_log.conflict = True
    export_log.conflict_reason = f"OF {order_number} ja exportada anteriormente para o Nomus"
    export_log.save(update_fields=["conflict", "conflict_reason", "updated_at"])
    return export_log


def record_sync_run_failure(run: NomusSyncRun | int, exc):
    run_id = run.pk if hasattr(run, "pk") else run
    with transaction.atomic():
        locked_run = NomusSyncRun.objects.select_for_update().get(pk=run_id)
        locked_run.status = NomusSyncRun.STATUS_FAILED
        locked_run.save(update_fields=["status"])

        export_log, _ = NomusExportLog.objects.select_for_update().get_or_create(sync_run=locked_run)
        export_log.status = NomusExportLog.STATUS_ERROR
        export_log.retry = bool(getattr(exc, "transient", False))
        export_log.attempts += 1
        export_log.error_message = str(exc)
        export_log.save(update_fields=["status", "retry", "attempts", "error_message", "updated_at"])
        return locked_run


def process_sync_run(run: NomusSyncRun, client=None):
    owns_client = client is None
    try:
        with transaction.atomic():
            run = NomusSyncRun.objects.select_for_update().get(pk=run.pk)
            if run.status == NomusSyncRun.STATUS_SUCCESS:
                return run

        client = client or _build_client()
        response = client.upsert_production_order(run.payload or {})
        remote_id = response.get("remote_id") or (run.payload or {}).get("order_number", "")

        with transaction.atomic():
            run = NomusSyncRun.objects.select_for_update().get(pk=run.pk)
            export_log, _ = NomusExportLog.objects.select_for_update().get_or_create(sync_run=run)
            export_log.remote_id = remote_id
            export_log.status = NomusExportLog.STATUS_EXPORTED
            export_log.retry = False
            export_log.error_message = ""
            export_log.attempts += 1
            export_log.save(update_fields=["remote_id", "status", "retry", "error_message", "attempts", "updated_at"])

            run.status = NomusSyncRun.STATUS_SUCCESS
            run.save(update_fields=["status"])

            _detect_and_flag_of_conflict(run)
            return run
    except Exception as exc:
        record_sync_run_failure(run, exc)
        raise
    finally:
        if owns_client:
            close = getattr(client, "close", None)
            if callable(close):
                close()
