import hashlib
import json
import logging

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.integrations.omie.client import HttpOmiePermanentError, build_omie_client, payload_digest
from apps.integrations.omie.models import (
    OmieFiscalDocument,
    OmieIntegrationConfig,
    OmieInvoiceAttempt,
    OmieInvoiceRun,
)
from apps.production.models import STATUS_CONCLUIDA, OrdemFabricacao

logger = logging.getLogger(__name__)

_BASE_FISCAL_DEFAULTS = {
    "base_url": "",
    "api_url": "",
    "natureza_operacao": "VENDA",
    "cfop": "5102",
    "regime_tributario": "simples_nacional",
    "cst_icms": "00",
    "cst_pis": "01",
    "cst_cofins": "01",
    "aliquota_icms": "0",
    "aliquota_pis": "0",
    "aliquota_cofins": "0",
}

_TERMINAL_RUN_STATUSES = {
    OmieInvoiceRun.STATUS_PENDING,
    OmieInvoiceRun.STATUS_PROCESSING,
    OmieInvoiceRun.STATUS_SUCCESS,
}

_REMOTE_ISSUED_STATUSES = {"issued", "authorized", "emitida", "autorizada"}


class OmieTaskEnqueueError(RuntimeError):
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
    return OmieIntegrationConfig.objects.filter(provider=OmieIntegrationConfig.PROVIDER, enabled=True).first()


def get_config():
    return OmieIntegrationConfig.objects.filter(provider=OmieIntegrationConfig.PROVIDER).order_by("-updated_at").first()


def _fiscal_defaults_snapshot(config: OmieIntegrationConfig | None):
    defaults = dict(_BASE_FISCAL_DEFAULTS)
    if config is not None:
        defaults.update(dict(config.fiscal_defaults or {}))
    return defaults


def _is_manual_trigger(trigger: str) -> bool:
    return str(trigger or "").strip().lower() == "admin"


def _response_confirms_issue(response):
    remote_status = str((response or {}).get("status") or "").strip().lower()
    remote_document_id = (response or {}).get("remote_document_id") or (response or {}).get("document_id") or ""
    remote_number = (response or {}).get("remote_number") or (response or {}).get("number") or ""
    if remote_status and remote_status not in _REMOTE_ISSUED_STATUSES:
        raise HttpOmiePermanentError(
            f"Omie returned non-issued status: {remote_status}",
            details={"response": response or {}},
        )
    if not remote_status and not (remote_document_id and remote_number):
        raise HttpOmiePermanentError(
            "Omie response did not confirm NF-e issuance",
            details={"response": response or {}},
        )
    return {
        "remote_status": remote_status or OmieFiscalDocument.STATUS_ISSUED,
        "remote_document_id": remote_document_id,
        "remote_number": remote_number,
    }


def serialize_nfe_from_of(of: OrdemFabricacao, config: OmieIntegrationConfig):
    if of.status != STATUS_CONCLUIDA:
        raise ValidationError("NF-e Omie só pode ser emitida para OF concluída.")

    quotation = of.quotation
    customer = quotation.customer
    defaults = _fiscal_defaults_snapshot(config)
    customer_snapshot = {
        "company_name": customer.company_name,
        "cnpj": customer.cnpj or defaults.get("customer_cnpj", ""),
        "email": customer.email or defaults.get("customer_email", ""),
        "city": customer.city or defaults.get("customer_city", ""),
        "state": customer.state or defaults.get("customer_state", ""),
        "contact_name": customer.contact_name or defaults.get("customer_contact_name", ""),
    }
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

    return {
        "provider": OmieIntegrationConfig.PROVIDER,
        "document_number": of.number,
        "order_number": of.number,
        "quotation_number": of.quotation_number,
        "quotation_revision": of.quotation_revision,
        "title": of.title,
        "scope": of.scope,
        "status": of.status,
        "company_code": config.company_code,
        "environment": config.environment,
        "customer": customer_snapshot,
        "customer_name": customer_snapshot["company_name"],
        "customer_cnpj": customer_snapshot["cnpj"],
        "customer_city": customer_snapshot["city"],
        "customer_state": customer_snapshot["state"],
        "gross_weight_kg": str(of.peso_bruto_kg),
        "net_weight_kg": str(of.peso_liquido_kg),
        "total_value": str(of.preco_com_impostos),
        "fiscal_defaults": defaults,
        "quotation": {
            "number": quotation.number,
            "revision": quotation.revision,
            "title": quotation.title,
            "scope": quotation.scope,
            "customer": {
                "company_name": quotation.customer.company_name,
                "cnpj": quotation.customer.cnpj,
                "email": quotation.customer.email,
                "city": quotation.customer.city,
                "state": quotation.customer.state,
            },
        },
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


def _get_or_build_document(of: OrdemFabricacao, config: OmieIntegrationConfig):
    payload = serialize_nfe_from_of(of, config)
    defaults_snapshot = _fiscal_defaults_snapshot(config)
    source_snapshot = _canonical_snapshot(payload["source_snapshot"])
    document, created = OmieFiscalDocument.objects.get_or_create(
        of=of,
        defaults={
            "config": config,
            "status": OmieFiscalDocument.STATUS_READY,
            "fiscal_defaults_snapshot": defaults_snapshot,
            "source_snapshot": source_snapshot,
            "payload": payload,
            "prepared_at": timezone.now(),
        },
    )
    if not created and document.status == OmieFiscalDocument.STATUS_ISSUED:
        return document
    changed = created
    if document.config_id != config.pk:
        document.config = config
        changed = True
    if document.status != OmieFiscalDocument.STATUS_ISSUED and document.status != OmieFiscalDocument.STATUS_READY:
        document.status = OmieFiscalDocument.STATUS_READY
        changed = True
    if document.payload != payload:
        document.payload = payload
        changed = True
    if document.fiscal_defaults_snapshot != defaults_snapshot:
        document.fiscal_defaults_snapshot = defaults_snapshot
        changed = True
    if document.source_snapshot != source_snapshot:
        document.source_snapshot = source_snapshot
        changed = True
    if not document.prepared_at:
        document.prepared_at = timezone.now()
        changed = True
    if changed:
        document.save(
            update_fields=[
                "config",
                "status",
                "fiscal_defaults_snapshot",
                "source_snapshot",
                "payload",
                "prepared_at",
                "updated_at",
            ]
        )
    return document


def maybe_enqueue_nfe_issue(of: OrdemFabricacao, trigger="of_completed"):
    if of.status != STATUS_CONCLUIDA:
        return None
    config = get_config()
    if config is None or not config.enabled:
        return None
    if not _is_manual_trigger(trigger) and not config.emit_on_of_completed:
        return None

    document = _get_or_build_document(of, config)
    latest_run = document.invoice_runs.order_by("-started_at", "-pk").first()
    if latest_run is not None and latest_run.status in _TERMINAL_RUN_STATUSES:
        return latest_run

    payload_hash_value = _payload_hash(document.payload or {})
    raw_key = ":".join([OmieIntegrationConfig.PROVIDER, str(of.pk), payload_hash_value])
    idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    run, created = OmieInvoiceRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "config": config,
            "document": document,
            "trigger": trigger,
            "payload": document.payload,
            "status": OmieInvoiceRun.STATUS_PENDING,
        },
    )
    if not created:
        changed = False
        if run.config_id != config.pk:
            run.config = config
            changed = True
        if run.document_id != document.pk:
            run.document = document
            changed = True
        if run.trigger != trigger:
            run.trigger = trigger
            changed = True
        if run.payload != document.payload:
            run.payload = document.payload
            changed = True
        if changed:
            run.save(update_fields=["config", "document", "trigger", "payload"])

    if document.status != OmieFiscalDocument.STATUS_READY:
        document.status = OmieFiscalDocument.STATUS_READY
        document.save(update_fields=["status", "updated_at"])
    return run


def mark_invoice_run_enqueue_failed(run_id, message):
    with transaction.atomic():
        run = OmieInvoiceRun.objects.select_for_update().select_related("document").get(pk=run_id)
        now = timezone.now()
        result_payload = dict(run.result_payload or {})
        result_payload.update({
            "status": "enqueue_failed",
            "enqueue_failed_at": now.isoformat(),
            "enqueue_error": message,
        })
        run.status = OmieInvoiceRun.STATUS_FAILED
        run.error_message = message
        run.result_payload = result_payload
        run.finished_at = now
        run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
        document = run.document
        if document.status != OmieFiscalDocument.STATUS_ISSUED:
            document.status = OmieFiscalDocument.STATUS_READY
            document.error_message = message
            document.result_payload = result_payload
            document.save(update_fields=["status", "error_message", "result_payload", "updated_at"])
        return run


def enqueue_invoice_run_async(run: OmieInvoiceRun, *, schema_name=None, raise_on_error=False):
    schema_name = schema_name or connection.schema_name
    from apps.integrations.omie.tasks import process_invoice_run

    try:
        process_invoice_run.delay(schema_name=schema_name, run_id=run.pk)
    except Exception:
        message = "Failed to enqueue Omie invoice run"
        logger.exception(
            message,
            extra={"schema_name": schema_name, "run_id": run.pk},
        )
        mark_invoice_run_enqueue_failed(run.pk, message)
        if raise_on_error:
            raise OmieTaskEnqueueError(message)
        return False
    return True


def record_invoice_run_failure(run_id, exc, *, response_payload=None):
    with transaction.atomic():
        run = OmieInvoiceRun.objects.select_for_update().select_related("document").get(pk=run_id)
        sequence = run.attempts.count() + 1
        result_payload = dict(run.result_payload or {})
        result_payload.update({
            "last_error_at": timezone.now().isoformat(),
            "last_error_type": exc.__class__.__name__,
            "transient": bool(getattr(exc, "transient", False)),
        })
        if response_payload:
            result_payload["last_error_response"] = response_payload
        OmieInvoiceAttempt.objects.create(
            run=run,
            sequence=sequence,
            status=OmieInvoiceAttempt.STATUS_FAILED,
            request_payload=run.payload or {},
            response_payload=response_payload or {},
            error_message=str(exc),
        )
        run.status = OmieInvoiceRun.STATUS_FAILED
        run.error_message = str(exc)
        run.result_payload = result_payload
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
        document = run.document
        document.status = OmieFiscalDocument.STATUS_FAILED
        document.error_message = str(exc)
        document.result_payload = result_payload
        document.save(update_fields=["status", "error_message", "result_payload", "updated_at"])
        return run


def reset_invoice_run_for_requeue(run):
    if run.status == OmieInvoiceRun.STATUS_PENDING:
        return False
    run.status = OmieInvoiceRun.STATUS_PENDING
    run.error_message = ""
    run.finished_at = None
    result_payload = dict(run.result_payload or {})
    result_payload["requeued_at"] = timezone.now().isoformat()
    run.result_payload = result_payload
    run.save(update_fields=["status", "error_message", "finished_at", "result_payload"])
    return True


def _mark_run_skipped(run: OmieInvoiceRun, message: str):
    now = timezone.now()
    run.status = OmieInvoiceRun.STATUS_SKIPPED
    run.error_message = message
    run.finished_at = now
    run.result_payload = {"status": "skipped", "reason": message}
    run.save(update_fields=["status", "error_message", "finished_at", "result_payload"])
    document = run.document
    if document.status != OmieFiscalDocument.STATUS_ISSUED:
        document.status = OmieFiscalDocument.STATUS_READY
        document.error_message = ""
        document.save(update_fields=["status", "error_message", "updated_at"])
    return run


def process_invoice_run(run: OmieInvoiceRun, client=None):
    owns_client = client is None
    try:
        with transaction.atomic():
            run = OmieInvoiceRun.objects.select_for_update().select_related(
                "document",
                "document__of",
                "document__of__quotation",
                "document__of__quotation__customer",
            ).get(pk=run.pk)
            document = run.document
            if run.status == OmieInvoiceRun.STATUS_SUCCESS:
                return run
            if document.status == OmieFiscalDocument.STATUS_ISSUED and document.remote_document_id:
                run.status = OmieInvoiceRun.STATUS_SUCCESS
                run.error_message = ""
                run.result_payload = document.result_payload or {
                    "status": "issued",
                    "remote_document_id": document.remote_document_id,
                    "remote_number": document.remote_number,
                }
                run.finished_at = timezone.now()
                run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
                return run

            config = run.config or get_enabled_config() or get_config()
            if config is None or not config.enabled:
                return _mark_run_skipped(run, "Omie integration is disabled")

            payload = run.payload or {}
            idempotency_key = run.idempotency_key
            run.status = OmieInvoiceRun.STATUS_PROCESSING
            run.error_message = ""
            run.finished_at = None
            run.save(update_fields=["status", "error_message", "finished_at"])

        if client is None:
            client = build_omie_client(config)
        response = client.issue_nfe(payload, idempotency_key=idempotency_key)
        remote_issue = _response_confirms_issue(response)

        with transaction.atomic():
            run = OmieInvoiceRun.objects.select_for_update().select_related("document").get(pk=run.pk)
            document = run.document
            if document.status == OmieFiscalDocument.STATUS_ISSUED and document.remote_document_id:
                if run.status != OmieInvoiceRun.STATUS_SUCCESS:
                    run.status = OmieInvoiceRun.STATUS_SUCCESS
                    run.error_message = ""
                    run.result_payload = document.result_payload or response
                    run.finished_at = timezone.now()
                    run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
                return run
            sequence = run.attempts.count() + 1
            OmieInvoiceAttempt.objects.create(
                run=run,
                sequence=sequence,
                status=OmieInvoiceAttempt.STATUS_SUCCESS,
                request_payload=payload,
                response_payload=response,
            )
            run.status = OmieInvoiceRun.STATUS_SUCCESS
            run.error_message = ""
            run.result_payload = response
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "result_payload", "finished_at"])
            document.status = OmieFiscalDocument.STATUS_ISSUED
            document.remote_document_id = remote_issue["remote_document_id"]
            document.remote_number = remote_issue["remote_number"]
            document.result_payload = response
            document.error_message = ""
            document.issued_at = timezone.now()
            document.save(
                update_fields=[
                    "status",
                    "remote_document_id",
                    "remote_number",
                    "result_payload",
                    "error_message",
                    "issued_at",
                    "updated_at",
                ]
            )
            return run
    except Exception as exc:
        record_invoice_run_failure(run.pk, exc)
        raise
    finally:
        if owns_client:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def run_healthcheck(config=None, client=None):
    config = config or get_enabled_config()
    checked_at = timezone.now()
    latest_run = OmieInvoiceRun.objects.order_by("-started_at").first()
    summary = {
        "enabled": bool(config and config.enabled),
        "checked_at": checked_at.isoformat(),
        "last_healthcheck_at": config.last_healthcheck_at.isoformat() if config and config.last_healthcheck_at else None,
        "pending_runs": OmieInvoiceRun.objects.filter(status=OmieInvoiceRun.STATUS_PENDING).count(),
        "failed_runs": OmieInvoiceRun.objects.filter(status=OmieInvoiceRun.STATUS_FAILED).count(),
        "latest_run_id": latest_run.pk if latest_run else None,
        "remote": {"status": "disabled"},
        "ok": False,
    }
    if config is None or not config.enabled:
        summary["remote"] = {"status": "disabled", "message": "Omie integration is disabled"}
        return summary
    owns_client = client is None
    client = client or build_omie_client(config)
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


serialize_invoice_payload = serialize_nfe_from_of
