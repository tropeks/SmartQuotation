from __future__ import annotations

import hashlib
import json
import logging

from django.db import connection, transaction
from django.utils import timezone

from apps.integrations.sap_b1.client import (
    HttpSapB1PermanentError,
    build_sap_b1_client,
    payload_digest,
)
from apps.integrations.sap_b1.models import (
    SapB1ExportLog,
    SapB1IntegrationConfig,
    SapB1SyncAttempt,
    SapB1SyncBinding,
    SapB1SyncRun,
)
from apps.production.models import OrdemFabricacao, STATUS_LIBERADA

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {
    SapB1SyncRun.STATUS_PENDING,
    SapB1SyncRun.STATUS_PROCESSING,
    SapB1SyncRun.STATUS_SUCCESS,
}


class SapB1TaskEnqueueError(RuntimeError):
    pass


def _payload_hash(payload):
    return payload_digest(payload)


def _canonical_snapshot(value):
    if isinstance(value, dict):
        return {str(key): _canonical_snapshot(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_snapshot(item) for item in value]
    return value


def get_enabled_config():
    return SapB1IntegrationConfig.objects.filter(provider=SapB1IntegrationConfig.PROVIDER, enabled=True).first()


def get_config():
    return SapB1IntegrationConfig.objects.filter(provider=SapB1IntegrationConfig.PROVIDER).order_by("-updated_at").first()


def _serialize_items(of: OrdemFabricacao):
    items = []
    for item in of.itens.prefetch_related("materiais", "operacoes").order_by("sort_order", "codigo_item", "pk"):
        items.append({
            "code": item.codigo_item,
            "description": item.descricao,
            "material_cost": str(item.custo_material),
            "labor_cost": str(item.custo_mo),
            "total_cost": str(item.custo_total),
            "materials": [
                {
                    "code": material.codigo_mp,
                    "description": material.descricao,
                    "material": material.material,
                    "shape": material.forma,
                    "gross_weight_kg": str(material.peso_bruto_kg),
                    "net_weight_kg": str(material.peso_liquido_kg),
                    "unit_price_kg": str(material.preco_kgf),
                    "cost": str(material.custo),
                }
                for material in item.materiais.order_by("codigo_mp", "pk")
            ],
            "operations": [
                {
                    "code": operation.codigo_op,
                    "description": operation.descricao,
                    "method": operation.metodo,
                    "cost": str(operation.custo),
                    "applicable": operation.aplicavel,
                    "sequence": operation.sequence,
                }
                for operation in item.operacoes.order_by("sequence", "codigo_op", "pk")
            ],
        })
    return items


def _get_sales_order_binding(of: OrdemFabricacao):
    return SapB1SyncBinding.objects.filter(
        provider=SapB1IntegrationConfig.PROVIDER,
        entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
        local_model="production.OrdemFabricacao",
        local_id=str(of.pk),
    ).first()


def serialize_sales_order_from_of(of: OrdemFabricacao):
    items = _serialize_items(of)
    return {
        "provider": SapB1IntegrationConfig.PROVIDER,
        "entity": SapB1SyncBinding.ENTITY_SALES_ORDER,
        "document_number": of.number,
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
        "items": items,
        "source_snapshot": {
            "of_number": of.number,
            "quotation_number": of.quotation_number,
            "quotation_revision": of.quotation_revision,
            "snapshot_hash": of.snapshot_hash,
            "customer_name": of.customer_name,
            "title": of.title,
            "scope": of.scope,
            "status": of.status,
        },
    }


def _run_payload(payload):
    return {key: value for key, value in payload.items() if key != "sap_doc_entry"}


def _execution_payload(run: SapB1SyncRun):
    payload = dict(run.payload or {})
    if run.entity_type != SapB1SyncBinding.ENTITY_SALES_ORDER:
        return payload
    if payload.get("sap_doc_entry"):
        return payload
    binding = SapB1SyncBinding.objects.filter(
        provider=SapB1IntegrationConfig.PROVIDER,
        entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
        local_model=run.local_model,
        local_id=run.local_id,
    ).first()
    if binding and binding.remote_code:
        payload["sap_doc_entry"] = binding.remote_code
    return payload


def serialize_bom_from_of(of: OrdemFabricacao):
    items = _serialize_items(of)
    return {
        "provider": SapB1IntegrationConfig.PROVIDER,
        "entity": SapB1SyncBinding.ENTITY_BOM,
        "bom_code": f"BOM-{of.number}",
        "document_number": of.number,
        "order_number": of.number,
        "items": items,
        "source_snapshot": {
            "of_number": of.number,
            "snapshot_hash": of.snapshot_hash,
            "title": of.title,
            "scope": of.scope,
            "status": of.status,
        },
    }


def _build_sync_run(direction, entity_type, local_model, local_id, payload, trigger):
    # `sap_doc_entry` is a post-export artifact (the remote code SAP returns and we
    # store on the binding), not source data. Including it in the idempotency hash
    # makes a re-export of an unchanged OF look different from the first export
    # (binding exists the 2nd time), spawning a duplicate run/log. Hash source only.
    stored_payload = _run_payload(payload)
    payload_hash = _payload_hash(stored_payload)
    raw_key = ":".join([
        SapB1IntegrationConfig.PROVIDER,
        direction,
        entity_type,
        str(local_model),
        str(local_id),
        payload_hash,
    ])
    idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    run, created = SapB1SyncRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "direction": direction,
            "entity_type": entity_type,
            "trigger": trigger,
            "local_model": local_model,
            "local_id": str(local_id),
            "payload_hash": payload_hash,
            "payload": stored_payload,
        },
    )
    if not created:
        changed = False
        if run.direction != direction:
            run.direction = direction
            changed = True
        if run.entity_type != entity_type:
            run.entity_type = entity_type
            changed = True
        if run.trigger != trigger:
            run.trigger = trigger
            changed = True
        if run.local_model != local_model:
            run.local_model = local_model
            changed = True
        if run.local_id != str(local_id):
            run.local_id = str(local_id)
            changed = True
        if run.payload_hash != payload_hash:
            run.payload_hash = payload_hash
            changed = True
        if run.payload != stored_payload:
            run.payload = stored_payload
            changed = True
        if changed:
            run.save(update_fields=["direction", "entity_type", "trigger", "local_model", "local_id", "payload_hash", "payload"])
    return run, created


def enqueue_sales_order_sync(of: OrdemFabricacao, trigger="manual"):
    payload = serialize_sales_order_from_of(of)
    return _build_sync_run(
        SapB1SyncRun.DIRECTION_PUSH,
        SapB1SyncBinding.ENTITY_SALES_ORDER,
        "production.OrdemFabricacao",
        of.pk,
        payload,
        trigger,
    )


def enqueue_bom_sync(of: OrdemFabricacao, trigger="manual"):
    payload = serialize_bom_from_of(of)
    return _build_sync_run(
        SapB1SyncRun.DIRECTION_PUSH,
        SapB1SyncBinding.ENTITY_BOM,
        "production.OrdemFabricacao",
        of.pk,
        payload,
        trigger,
    )


def maybe_enqueue_sales_order_sync(of: OrdemFabricacao, trigger="admin"):
    if of.status != STATUS_LIBERADA:
        return None
    config = get_enabled_config()
    if config is None or not config.sync_sales_orders_enabled:
        return None
    run, _ = enqueue_sales_order_sync(of, trigger=trigger)
    return run


def maybe_enqueue_bom_sync(of: OrdemFabricacao, trigger="admin"):
    if of.status != STATUS_LIBERADA:
        return None
    config = get_enabled_config()
    if config is None or not config.sync_boms_enabled:
        return None
    run, _ = enqueue_bom_sync(of, trigger=trigger)
    return run


def enqueue_sync_run_async(run: SapB1SyncRun, *, schema_name=None, raise_on_error=False):
    schema_name = schema_name or connection.schema_name
    from apps.integrations.sap_b1.tasks import process_sap_b1_sync_run

    try:
        process_sap_b1_sync_run.delay(schema_name=schema_name, run_id=run.pk)
    except Exception:
        message = "Failed to enqueue SAP B1 sync run"
        logger.exception(
            message,
            extra={"schema_name": schema_name, "run_id": run.pk},
        )
        mark_sync_run_enqueue_failed(run.pk, message)
        if raise_on_error:
            raise SapB1TaskEnqueueError(message)
        return False
    return True


def mark_sync_run_enqueue_failed(run_id, message):
    with transaction.atomic():
        run = SapB1SyncRun.objects.select_for_update().get(pk=run_id)
        now = timezone.now()
        result_payload = dict(run.result_payload or {})
        result_payload.update({
            "status": "enqueue_failed",
            "enqueue_failed_at": now.isoformat(),
            "enqueue_error": message,
        })
        run.status = SapB1SyncRun.STATUS_FAILED
        run.error_message = message
        run.result_payload = result_payload
        run.finished_at = now
        run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
        return run


def record_sync_run_failure(run_id, exc, *, response_payload=None):
    with transaction.atomic():
        run = SapB1SyncRun.objects.select_for_update().get(pk=run_id)
        payload = run.payload or {}
        sequence = run.attempts.count() + 1
        result_payload = dict(run.result_payload or {})
        result_payload.update({
            "last_error_at": timezone.now().isoformat(),
            "last_error_type": exc.__class__.__name__,
            "transient": bool(getattr(exc, "transient", False)),
        })
        if response_payload:
            result_payload["last_error_response"] = response_payload
        SapB1SyncAttempt.objects.create(
            run=run,
            sequence=sequence,
            status=SapB1SyncAttempt.STATUS_FAILED,
            request_payload=payload,
            response_payload=response_payload or {},
            error_message=str(exc),
        )
        run.status = SapB1SyncRun.STATUS_FAILED
        run.error_message = str(exc)
        run.result_payload = result_payload
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
        return run


def _response_remote_code(response, payload):
    r = response or {}
    doc_entry = r.get("DocEntry")
    return (
        r.get("remote_code")
        or r.get("remote_id")
        or (str(doc_entry) if doc_entry is not None else None)
        or payload.get("sap_doc_entry")
        or r.get("number")
        or payload.get("order_number")
        or payload.get("document_number")
        or payload.get("bom_code")
        or ""
    )


def _upsert_binding(entity_type, local_model, local_id, remote_code, payload, metadata=None):
    defaults = {
        "remote_code": remote_code,
        "payload_hash": _payload_hash(payload),
        "last_direction": SapB1SyncBinding.DIRECTION_PUSH,
        "source_of_truth": SapB1SyncBinding.SOURCE_LOCAL,
        "metadata": metadata or {},
    }
    binding = (
        SapB1SyncBinding.objects.filter(
            provider=SapB1IntegrationConfig.PROVIDER,
            entity_type=entity_type,
            local_model=local_model,
            local_id=str(local_id),
        ).first()
        or SapB1SyncBinding.objects.filter(
            provider=SapB1IntegrationConfig.PROVIDER,
            entity_type=entity_type,
            remote_code=remote_code,
        ).first()
    )
    if binding is None:
        binding = SapB1SyncBinding(
            provider=SapB1IntegrationConfig.PROVIDER,
            entity_type=entity_type,
            local_model=local_model,
            local_id=str(local_id),
        )
    else:
        binding.local_model = local_model
        binding.local_id = str(local_id)
    for field, value in defaults.items():
        setattr(binding, field, value)
    binding.save()
    return binding


def _mark_run_skipped(run: SapB1SyncRun, message: str):
    now = timezone.now()
    run.status = SapB1SyncRun.STATUS_SKIPPED
    run.error_message = message
    run.finished_at = now
    run.result_payload = {"status": "skipped", "reason": message}
    run.save(update_fields=["status", "error_message", "finished_at", "result_payload"])
    return run


def process_sync_run(run: SapB1SyncRun, client=None):
    owns_client = client is None
    try:
        with transaction.atomic():
            run = SapB1SyncRun.objects.select_for_update().get(pk=run.pk)
            if run.status == SapB1SyncRun.STATUS_SUCCESS:
                return run

            config = get_enabled_config()
            if config is None or not config.enabled:
                return _mark_run_skipped(run, "SAP B1 integration is disabled")

            payload = _execution_payload(run)
            sequence = run.attempts.count() + 1
            run.status = SapB1SyncRun.STATUS_PROCESSING
            run.error_message = ""
            run.finished_at = None
            run.save(update_fields=["status", "error_message", "finished_at"])

        if client is None:
            client = build_sap_b1_client(config=config)

        if run.entity_type == SapB1SyncBinding.ENTITY_SALES_ORDER:
            response = client.upsert_sales_order(payload)
            metadata = {"document_number": payload.get("document_number", "")}
        elif run.entity_type == SapB1SyncBinding.ENTITY_BOM:
            response = client.upsert_bom(payload)
            metadata = {"order_number": payload.get("order_number", ""), "bom_code": payload.get("bom_code", "")}
        else:
            raise ValueError(f"Unsupported entity type: {run.entity_type}")

        remote_code = _response_remote_code(response, payload)

        with transaction.atomic():
            run = SapB1SyncRun.objects.select_for_update().get(pk=run.pk)
            if run.status == SapB1SyncRun.STATUS_SUCCESS:
                return run
            SapB1SyncAttempt.objects.create(
                run=run,
                sequence=sequence,
                status=SapB1SyncAttempt.STATUS_SUCCESS,
                request_payload=payload,
                response_payload=response,
            )
            _upsert_binding(
                run.entity_type,
                run.local_model,
                run.local_id,
                remote_code,
                payload,
                metadata=metadata,
            )
            if run.entity_type == SapB1SyncBinding.ENTITY_SALES_ORDER:
                SapB1ExportLog.objects.get_or_create(
                    sync_run=run,
                    defaults={
                        "sap_doc_entry": remote_code,
                        "sap_status": SapB1ExportLog.SAP_STATUS_PENDING,
                    },
                )
            run.status = SapB1SyncRun.STATUS_SUCCESS
            run.remote_code = remote_code
            run.result_payload = response
            run.error_message = ""
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "remote_code", "result_payload", "error_message", "finished_at"])
            return run
    except Exception as exc:
        record_sync_run_failure(run.pk, exc)
        raise
    finally:
        if owns_client:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def reset_sync_run_for_requeue(run):
    with transaction.atomic():
        run = SapB1SyncRun.objects.select_for_update().get(pk=run.pk)
        if run.status in {
            SapB1SyncRun.STATUS_PENDING,
            SapB1SyncRun.STATUS_SUCCESS,
        }:
            return False
        result_payload = dict(run.result_payload or {})
        result_payload["requeued_at"] = timezone.now().isoformat()
        run.status = SapB1SyncRun.STATUS_PENDING
        run.error_message = ""
        run.finished_at = None
        run.result_payload = result_payload
        run.save(update_fields=["status", "error_message", "finished_at", "result_payload"])
    return True


def run_healthcheck(config=None, client=None):
    config = config or get_enabled_config() or get_config()
    checked_at = timezone.now()
    latest_run = SapB1SyncRun.objects.order_by("-started_at").first()
    summary = {
        "enabled": bool(config and config.enabled),
        "checked_at": checked_at.isoformat(),
        "last_healthcheck_at": config.last_healthcheck_at.isoformat() if config and config.last_healthcheck_at else None,
        "pending_runs": SapB1SyncRun.objects.filter(status=SapB1SyncRun.STATUS_PENDING).count(),
        "failed_runs": SapB1SyncRun.objects.filter(status=SapB1SyncRun.STATUS_FAILED).count(),
        "latest_run_id": latest_run.pk if latest_run else None,
        "remote": {"status": "disabled"},
        "ok": False,
    }
    if config is None or not config.enabled:
        summary["remote"] = {"status": "disabled", "message": "SAP B1 integration is disabled"}
        return summary
    owns_client = client is None
    client = client or build_sap_b1_client(config)
    try:
        summary["remote"] = {"status": "ok", "payload": client.healthcheck()}
        summary["ok"] = True
    except Exception as exc:
        summary["remote"] = {
            "status": "error",
            "message": str(exc),
            "transient": bool(getattr(exc, "transient", False)),
            "error_type": exc.__class__.__name__,
        }
    finally:
        config.last_healthcheck_at = checked_at
        config.save(update_fields=["last_healthcheck_at", "updated_at"])
        if owns_client:
            close = getattr(client, "close", None)
            if callable(close):
                close()
    return summary


def _on_of_pre_save(sender, instance, **kwargs):
    """Stash the current DB status so post_save can detect CONCLUIDA transitions."""
    if instance.pk:
        try:
            instance._pre_save_status = (
                sender.objects.filter(pk=instance.pk).values_list("status", flat=True).get()
            )
        except sender.DoesNotExist:
            instance._pre_save_status = None
    else:
        instance._pre_save_status = None


def _detect_and_flag_of_conflict(of):
    """Flag SapB1ExportLog.conflict when critical OF fields changed after a successful export."""
    successful_run = (
        SapB1SyncRun.objects.filter(
            entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
            local_model="production.OrdemFabricacao",
            local_id=str(of.pk),
            status=SapB1SyncRun.STATUS_SUCCESS,
        )
        .order_by("-started_at")
        .first()
    )
    if successful_run is None:
        return

    try:
        export_log = successful_run.export_log
    except SapB1ExportLog.DoesNotExist:
        return

    if export_log.conflict:
        return

    payload = successful_run.payload or {}
    source_snapshot = payload.get("source_snapshot", {})

    changed_fields = []
    if payload.get("status") != of.status:
        changed_fields.append("status")
    if source_snapshot.get("snapshot_hash") != of.snapshot_hash:
        changed_fields.append("snapshot_hash")
    if _payload_hash(payload.get("items", [])) != _payload_hash(_serialize_items(of)):
        changed_fields.append("items")

    for field in ["customer_name", "title", "scope"]:
        if field in source_snapshot and source_snapshot[field] != getattr(of, field, None):
            changed_fields.append(field)

    if "of_number" in source_snapshot and source_snapshot["of_number"] != of.number:
        changed_fields.append("number")
        
    if "totals" in payload:
        totals = payload["totals"]
        if totals.get("custo_material") != str(of.custo_material):
            changed_fields.append("custo_material")
        if totals.get("custo_mo") != str(of.custo_mo):
            changed_fields.append("custo_mo")
        if totals.get("custo_total") != str(of.custo_total):
            changed_fields.append("custo_total")
        if totals.get("preco_com_impostos") != str(of.preco_com_impostos):
            changed_fields.append("preco_com_impostos")

    if not changed_fields:
        return

    reason = f"Campos alterados após exportação: {', '.join(changed_fields)}"
    export_log.conflict = True
    export_log.conflict_reason = reason
    export_log.save(update_fields=["conflict", "conflict_reason", "updated_at"])
    logger.warning(
        "SAP B1 conflito detectado: OF %s editada após exportação. Campos: %s. ExportLog pk=%s",
        of.pk,
        ", ".join(changed_fields),
        export_log.pk,
    )


def _dispatch_export_of_task(of_id, schema_name):
    from apps.integrations.sap_b1.tasks import export_of_to_sap_b1

    try:
        export_of_to_sap_b1.delay(schema_name=schema_name, of_id=of_id)
    except Exception:
        logger.exception(
            "Failed to enqueue export_of_to_sap_b1",
            extra={"schema_name": schema_name, "of_id": of_id},
        )


def _on_of_post_save(sender, instance, created, **kwargs):
    """Detect conflicts on exported OFs and auto-export on CONCLUIDA transition."""
    from apps.production.models import STATUS_CONCLUIDA

    # Conflict detection: check if a previously exported OF was edited
    if not created:
        _detect_and_flag_of_conflict(instance)

    if instance.status != STATUS_CONCLUIDA:
        return
    pre_status = getattr(instance, "_pre_save_status", None)
    if not created and pre_status == STATUS_CONCLUIDA:
        return  # no status transition
    config = get_enabled_config()
    if config is None or not config.auto_export:
        return
    # Idempotency: skip if already successfully auto-exported
    if SapB1SyncRun.objects.filter(
        local_model="production.OrdemFabricacao",
        local_id=str(instance.pk),
        trigger="auto_export",
        status=SapB1SyncRun.STATUS_SUCCESS,
    ).exists():
        return
    of_id = instance.pk
    schema_name = connection.schema_name
    transaction.on_commit(lambda: _dispatch_export_of_task(of_id, schema_name))


serialize_sales_order_payload = serialize_sales_order_from_of
serialize_bom_payload = serialize_bom_from_of
