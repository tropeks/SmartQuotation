import hashlib
import json
import logging

from django.db import transaction
from django.db import connection
from django.utils import timezone

from apps.integrations.protheus.client import build_protheus_client
from apps.integrations.protheus.models import (
    ProtheusCatalogStaging,
    ProtheusBOMSnapshot,
    ProtheusIntegrationConfig,
    ProtheusSupplier,
    ProtheusSyncAttempt,
    ProtheusSyncBinding,
    ProtheusSyncRun,
    ProtheusWorkOrderSnapshot,
)
from apps.materials.models import Material, MaterialPrice
from apps.production.models import OrdemFabricacao

logger = logging.getLogger(__name__)


def _payload_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_enabled_config():
    return ProtheusIntegrationConfig.objects.filter(enabled=True).first()


def serialize_work_order(of: OrdemFabricacao):
    itens = []
    for item in of.itens.prefetch_related("materiais", "operacoes").all():
        itens.append({
            "code": item.codigo_item,
            "description": item.descricao,
            "material_cost": str(item.custo_material),
            "labor_cost": str(item.custo_mo),
            "materials": [
                {
                    "code": material.codigo_mp,
                    "description": material.descricao,
                    "spec": material.material,
                    "shape": material.forma,
                    "gross_weight_kg": str(material.peso_bruto_kg),
                    "net_weight_kg": str(material.peso_liquido_kg),
                    "unit_price_kg": str(material.preco_kgf),
                    "cost": str(material.custo),
                }
                for material in item.materiais.all()
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
                for operation in item.operacoes.all()
            ],
        })
    return {
        "number": of.number,
        "quotation_number": of.quotation_number,
        "quotation_revision": of.quotation_revision,
        "snapshot_hash": of.snapshot_hash,
        "customer_name": of.customer_name,
        "title": of.title,
        "scope": of.scope,
        "status": of.status,
        "material_cost": str(of.custo_material),
        "labor_cost": str(of.custo_mo),
        "total_cost": str(of.custo_total),
        "sale_price": str(of.preco_com_impostos),
        "gross_weight_kg": str(of.peso_bruto_kg),
        "net_weight_kg": str(of.peso_liquido_kg),
        "items": itens,
    }


def serialize_material(material: Material, price: MaterialPrice | None = None):
    payload = {
        "code": material.sigla,
        "description": material.tipo or material.sigla,
        "spec": material.sigla,
        "norm": material.norma,
        "default_shape": material.forma_padrao,
        "is_active": material.is_active,
    }
    if price is not None:
        payload.update({
            "shape": price.forma,
            "unit_price_kg": str(price.preco_brl_kg),
            "supplier_name": price.fornecedor,
            "valid_from": price.valid_from.isoformat(),
            "valid_until": price.valid_until.isoformat() if price.valid_until else None,
        })
    return payload


def serialize_supplier(supplier: ProtheusSupplier):
    return {
        "code": supplier.supplier_code,
        "legal_name": supplier.legal_name,
        "cnpj": supplier.cnpj,
        "email": supplier.email,
        "phone": supplier.phone,
        "city": supplier.city,
        "state": supplier.state,
        "is_active": supplier.is_active,
    }


def _build_sync_run(direction, entity_type, local_model, local_id, payload, trigger):
    payload_hash = _payload_hash(payload)
    raw_key = ":".join([
        ProtheusIntegrationConfig.PROVIDER,
        direction,
        entity_type,
        str(local_model),
        str(local_id),
        payload_hash,
    ])
    idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    run, created = ProtheusSyncRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "direction": direction,
            "entity_type": entity_type,
            "trigger": trigger,
            "local_model": local_model,
            "local_id": str(local_id),
            "payload_hash": payload_hash,
            "payload": payload,
        },
    )
    return run, created


def enqueue_work_order_export(of: OrdemFabricacao, trigger="manual"):
    payload = serialize_work_order(of)
    return _build_sync_run(
        ProtheusSyncRun.DIRECTION_PUSH,
        ProtheusSyncBinding.ENTITY_WORK_ORDER,
        "production.OrdemFabricacao",
        of.pk,
        payload,
        trigger,
    )


def enqueue_material_export(material: Material, price: MaterialPrice | None = None, trigger="manual"):
    payload = serialize_material(material, price=price)
    return _build_sync_run(
        ProtheusSyncRun.DIRECTION_PUSH,
        ProtheusSyncBinding.ENTITY_MATERIAL,
        "materials.Material",
        material.pk,
        payload,
        trigger,
    )


def enqueue_supplier_export(supplier: ProtheusSupplier, trigger="manual"):
    payload = serialize_supplier(supplier)
    return _build_sync_run(
        ProtheusSyncRun.DIRECTION_PUSH,
        ProtheusSyncBinding.ENTITY_SUPPLIER,
        "protheus.ProtheusSupplier",
        supplier.pk,
        payload,
        trigger,
    )


def maybe_enqueue_work_order_export(of: OrdemFabricacao, trigger="status_transition"):
    config = get_enabled_config()
    if config is None or not config.export_on_release:
        return None
    run, _ = enqueue_work_order_export(of, trigger=trigger)
    return run


def enqueue_sync_run_async(run: ProtheusSyncRun, *, schema_name=None):
    schema_name = schema_name or connection.schema_name
    from apps.integrations.protheus.tasks import process_protheus_sync_run

    try:
        process_protheus_sync_run.delay(schema_name=schema_name, run_id=run.pk)
    except Exception:
        logger.exception(
            "Failed to enqueue Protheus sync run",
            extra={"schema_name": schema_name, "run_id": run.pk},
        )
    return run


@transaction.atomic
def process_sync_run(run: ProtheusSyncRun, client=None):
    if client is None:
        client = build_protheus_client(get_enabled_config())
    run = ProtheusSyncRun.objects.select_for_update().get(pk=run.pk)
    if run.status == ProtheusSyncRun.STATUS_SUCCESS:
        return run

    payload = run.payload or {}
    sequence = run.attempts.count() + 1
    try:
        if run.entity_type == ProtheusSyncBinding.ENTITY_WORK_ORDER:
            response = client.upsert_work_order(payload)
            _record_work_order_binding(run, response)
        elif run.entity_type == ProtheusSyncBinding.ENTITY_MATERIAL:
            response = client.upsert_material(payload)
            _record_material_binding(run, response)
        elif run.entity_type == ProtheusSyncBinding.ENTITY_SUPPLIER:
            response = client.upsert_supplier(payload)
            _record_supplier_binding(run, response)
        else:
            raise ValueError(f"Unsupported entity type: {run.entity_type}")

        ProtheusSyncAttempt.objects.create(
            run=run,
            sequence=sequence,
            status=ProtheusSyncAttempt.STATUS_SUCCESS,
            request_payload=payload,
            response_payload=response,
        )
        remote_code = (
            response.get("remote_code")
            or payload.get("number")
            or payload.get("code")
            or ""
        )
        run.status = ProtheusSyncRun.STATUS_SUCCESS
        run.remote_code = remote_code
        run.result_payload = response
        run.error_message = ""
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "remote_code", "result_payload", "error_message", "finished_at"])
        return run
    except Exception as exc:
        ProtheusSyncAttempt.objects.create(
            run=run,
            sequence=sequence,
            status=ProtheusSyncAttempt.STATUS_FAILED,
            request_payload=payload,
            response_payload={},
            error_message=str(exc),
        )
        run.status = ProtheusSyncRun.STATUS_FAILED
        run.error_message = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])
        raise


def _upsert_binding(entity_type, local_model, local_id, remote_code, direction, payload, metadata=None):
    defaults = {
        "remote_code": remote_code,
        "payload_hash": _payload_hash(payload),
        "last_direction": direction,
        "source_of_truth": (
            ProtheusSyncBinding.SOURCE_LOCAL
            if direction == ProtheusSyncBinding.DIRECTION_PUSH
            else ProtheusSyncBinding.SOURCE_REMOTE
        ),
        "metadata": metadata or {},
    }
    binding = (
        ProtheusSyncBinding.objects.filter(
            provider=ProtheusIntegrationConfig.PROVIDER,
            entity_type=entity_type,
            local_model=local_model,
            local_id=str(local_id),
        ).first()
        or ProtheusSyncBinding.objects.filter(
            provider=ProtheusIntegrationConfig.PROVIDER,
            entity_type=entity_type,
            remote_code=remote_code,
        ).first()
    )
    if binding is None:
        binding = ProtheusSyncBinding(
            provider=ProtheusIntegrationConfig.PROVIDER,
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


def _record_work_order_binding(run, response):
    payload = run.payload
    remote_code = response.get("remote_code", payload["number"])
    _upsert_binding(
        ProtheusSyncBinding.ENTITY_WORK_ORDER,
        run.local_model,
        run.local_id,
        remote_code,
        ProtheusSyncBinding.DIRECTION_PUSH,
        payload,
    )
    _upsert_binding(
        ProtheusSyncBinding.ENTITY_BOM,
        run.local_model,
        run.local_id,
        response.get("bom_code") or f"BOM-{remote_code}",
        ProtheusSyncBinding.DIRECTION_PUSH,
        {"items": payload.get("items", [])},
        metadata={"work_order_code": remote_code},
    )


def _record_material_binding(run, response):
    remote_code = response.get("remote_code") or run.payload.get("code", "")
    _upsert_binding(
        ProtheusSyncBinding.ENTITY_MATERIAL,
        run.local_model,
        run.local_id,
        remote_code,
        ProtheusSyncBinding.DIRECTION_PUSH,
        run.payload,
    )


def _record_supplier_binding(run, response):
    remote_code = response.get("remote_code") or run.payload.get("code", "")
    _upsert_binding(
        ProtheusSyncBinding.ENTITY_SUPPLIER,
        run.local_model,
        run.local_id,
        remote_code,
        ProtheusSyncBinding.DIRECTION_PUSH,
        run.payload,
    )


@transaction.atomic
def import_suppliers(payloads, trigger="pull"):
    imported = []
    for payload in payloads:
        supplier, _ = ProtheusSupplier.objects.update_or_create(
            supplier_code=payload["code"],
            defaults={
                "legal_name": payload.get("legal_name", ""),
                "cnpj": payload.get("cnpj", ""),
                "email": payload.get("email", ""),
                "phone": payload.get("phone", ""),
                "city": payload.get("city", ""),
                "state": payload.get("state", ""),
                "is_active": payload.get("is_active", True),
                "payload": payload,
            },
        )
        _upsert_binding(
            ProtheusSyncBinding.ENTITY_SUPPLIER,
            "protheus.ProtheusSupplier",
            supplier.pk,
            supplier.supplier_code,
            ProtheusSyncBinding.DIRECTION_PULL,
            payload,
        )
        run, _ = _build_sync_run(
            ProtheusSyncRun.DIRECTION_PULL,
            ProtheusSyncBinding.ENTITY_SUPPLIER,
            "protheus.ProtheusSupplier",
            supplier.pk,
            payload,
            trigger,
        )
        if run.status != ProtheusSyncRun.STATUS_SUCCESS:
            run.status = ProtheusSyncRun.STATUS_SUCCESS
            run.remote_code = supplier.supplier_code
            run.result_payload = {"imported": True}
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "remote_code", "result_payload", "finished_at"])
        imported.append(supplier)
    return imported


@transaction.atomic
def import_materials(payloads, trigger="pull"):
    imported = []
    for payload in payloads:
        material, _ = Material.objects.update_or_create(
            sigla=payload["code"],
            defaults={
                "tipo": payload.get("description", ""),
                "norma": payload.get("norm", ""),
                "forma_padrao": payload.get("shape") or payload.get("default_shape", ""),
                "is_active": payload.get("is_active", True),
            },
        )
        valid_from = payload.get("valid_from") or timezone.localdate().isoformat()
        defaults = {
            "preco_brl_kg": str(payload.get("unit_price_kg", "0")),
            "fornecedor": payload.get("supplier_name", ""),
            "valid_until": payload.get("valid_until") or None,
        }
        MaterialPrice.objects.update_or_create(
            material=material,
            forma=payload.get("shape") or material.forma_padrao or "chapa",
            valid_from=valid_from,
            defaults=defaults,
        )
        _upsert_binding(
            ProtheusSyncBinding.ENTITY_MATERIAL,
            "materials.Material",
            material.pk,
            payload["code"],
            ProtheusSyncBinding.DIRECTION_PULL,
            payload,
        )
        run, _ = _build_sync_run(
            ProtheusSyncRun.DIRECTION_PULL,
            ProtheusSyncBinding.ENTITY_MATERIAL,
            "materials.Material",
            material.pk,
            payload,
            trigger,
        )
        if run.status != ProtheusSyncRun.STATUS_SUCCESS:
            run.status = ProtheusSyncRun.STATUS_SUCCESS
            run.remote_code = payload["code"]
            run.result_payload = {"imported": True}
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "remote_code", "result_payload", "finished_at"])
        imported.append(material)
    return imported


@transaction.atomic
def import_work_orders(payloads, trigger="pull"):
    imported = []
    for payload in payloads:
        remote_code = payload["number"]
        work_order, _ = ProtheusWorkOrderSnapshot.objects.update_or_create(
            remote_code=remote_code,
            defaults={
                "title": payload.get("title", ""),
                "customer_name": payload.get("customer_name", ""),
                "status": payload.get("status", ""),
                "payload": payload,
            },
        )
        ProtheusBOMSnapshot.objects.update_or_create(
            work_order=work_order,
            defaults={"payload": {"items": payload.get("items", [])}},
        )
        _upsert_binding(
            ProtheusSyncBinding.ENTITY_WORK_ORDER,
            "protheus.ProtheusWorkOrderSnapshot",
            work_order.pk,
            remote_code,
            ProtheusSyncBinding.DIRECTION_PULL,
            payload,
        )
        _upsert_binding(
            ProtheusSyncBinding.ENTITY_BOM,
            "protheus.ProtheusWorkOrderSnapshot",
            work_order.pk,
            f"BOM-{remote_code}",
            ProtheusSyncBinding.DIRECTION_PULL,
            {"items": payload.get("items", [])},
            metadata={"work_order_code": remote_code},
        )
        run, _ = _build_sync_run(
            ProtheusSyncRun.DIRECTION_PULL,
            ProtheusSyncBinding.ENTITY_WORK_ORDER,
            "protheus.ProtheusWorkOrderSnapshot",
            work_order.pk,
            payload,
            trigger,
        )
        if run.status != ProtheusSyncRun.STATUS_SUCCESS:
            run.status = ProtheusSyncRun.STATUS_SUCCESS
            run.remote_code = remote_code
            run.result_payload = {"imported": True}
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "remote_code", "result_payload", "finished_at"])
        imported.append(work_order)
    return imported


def _stage_catalog_payload(entity_type, payload, trigger="pull"):
    remote_code = payload["code"]
    payload_hash = _payload_hash(payload)
    staging, _ = ProtheusCatalogStaging.objects.get_or_create(
        provider=ProtheusIntegrationConfig.PROVIDER,
        entity_type=entity_type,
        remote_code=remote_code,
        payload_hash=payload_hash,
        defaults={
            "payload": payload,
            "status": ProtheusCatalogStaging.STATUS_PENDING,
        },
    )
    if staging.payload != payload:
        staging.payload = payload
        staging.save(update_fields=["payload", "updated_at"])

    run, _ = _build_sync_run(
        ProtheusSyncRun.DIRECTION_PULL,
        entity_type,
        "protheus.ProtheusCatalogStaging",
        staging.pk,
        payload,
        trigger,
    )
    if run.status != ProtheusSyncRun.STATUS_SUCCESS:
        run.status = ProtheusSyncRun.STATUS_SUCCESS
        run.remote_code = remote_code
        run.result_payload = {"staged": True, "staging_id": staging.pk}
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "remote_code", "result_payload", "finished_at"])

    if staging.source_run_id != run.pk:
        staging.source_run = run
        staging.save(update_fields=["source_run", "updated_at"])
    return staging


@transaction.atomic
def stage_suppliers(payloads, trigger="pull"):
    return [_stage_catalog_payload(ProtheusCatalogStaging.ENTITY_SUPPLIER, payload, trigger=trigger) for payload in payloads]


@transaction.atomic
def stage_materials(payloads, trigger="pull"):
    return [_stage_catalog_payload(ProtheusCatalogStaging.ENTITY_MATERIAL, payload, trigger=trigger) for payload in payloads]


@transaction.atomic
def apply_catalog_staging(staging, actor=None):
    staging = ProtheusCatalogStaging.objects.select_for_update().get(pk=staging.pk)
    payload = staging.payload or {}
    now = timezone.now()
    if staging.entity_type == ProtheusCatalogStaging.ENTITY_MATERIAL:
        material, _ = Material.objects.update_or_create(
            sigla=payload["code"],
            defaults={
                "tipo": payload.get("description", ""),
                "norma": payload.get("norm", ""),
                "forma_padrao": payload.get("shape") or payload.get("default_shape", ""),
                "is_active": payload.get("is_active", True),
            },
        )
        valid_from = payload.get("valid_from") or timezone.localdate().isoformat()
        MaterialPrice.objects.update_or_create(
            material=material,
            forma=payload.get("shape") or material.forma_padrao or "chapa",
            valid_from=valid_from,
            defaults={
                "preco_brl_kg": str(payload.get("unit_price_kg", "0")),
                "fornecedor": payload.get("supplier_name", ""),
                "valid_until": payload.get("valid_until") or None,
            },
        )
        _upsert_binding(
            ProtheusSyncBinding.ENTITY_MATERIAL,
            "materials.Material",
            material.pk,
            payload["code"],
            ProtheusSyncBinding.DIRECTION_PULL,
            payload,
        )
        staging.applied_object_model = "materials.Material"
        staging.applied_object_id = str(material.pk)
    elif staging.entity_type == ProtheusCatalogStaging.ENTITY_SUPPLIER:
        supplier, _ = ProtheusSupplier.objects.update_or_create(
            supplier_code=payload["code"],
            defaults={
                "legal_name": payload.get("legal_name", ""),
                "cnpj": payload.get("cnpj", ""),
                "email": payload.get("email", ""),
                "phone": payload.get("phone", ""),
                "city": payload.get("city", ""),
                "state": payload.get("state", ""),
                "is_active": payload.get("is_active", True),
                "payload": payload,
            },
        )
        _upsert_binding(
            ProtheusSyncBinding.ENTITY_SUPPLIER,
            "protheus.ProtheusSupplier",
            supplier.pk,
            payload["code"],
            ProtheusSyncBinding.DIRECTION_PULL,
            payload,
        )
        staging.applied_object_model = "protheus.ProtheusSupplier"
        staging.applied_object_id = str(supplier.pk)
    else:
        raise ValueError(f"Unsupported staging entity type: {staging.entity_type}")

    staging.status = ProtheusCatalogStaging.STATUS_APPLIED
    staging.error_message = ""
    staging.reviewed_by = actor if getattr(actor, "pk", None) else None
    staging.reviewed_at = now
    staging.applied_at = now
    staging.rejected_at = None
    staging.save(
        update_fields=[
            "status",
            "applied_object_model",
            "applied_object_id",
            "error_message",
            "reviewed_by",
            "reviewed_at",
            "applied_at",
            "rejected_at",
            "updated_at",
        ]
    )
    return staging


@transaction.atomic
def reject_catalog_staging(staging, actor=None, reason=""):
    staging = ProtheusCatalogStaging.objects.select_for_update().get(pk=staging.pk)
    now = timezone.now()
    staging.status = ProtheusCatalogStaging.STATUS_REJECTED
    staging.error_message = reason or staging.error_message
    staging.reviewed_by = actor if getattr(actor, "pk", None) else None
    staging.reviewed_at = now
    staging.rejected_at = now
    staging.save(
        update_fields=[
            "status",
            "error_message",
            "reviewed_by",
            "reviewed_at",
            "rejected_at",
            "updated_at",
        ]
    )
    return staging


def pull_from_client(client, config=None):
    config = config or get_enabled_config()
    if config is None or not config.enabled:
        return {"suppliers": [], "materials": [], "work_orders": []}
    imported = {
        "suppliers": stage_suppliers(client.list_suppliers()) if config.pull_suppliers_enabled else [],
        "materials": stage_materials(client.list_materials()) if config.pull_materials_enabled else [],
        "work_orders": import_work_orders(client.list_work_orders()) if config.pull_work_orders_enabled else [],
    }
    return imported
