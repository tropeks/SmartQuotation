"""Interface pública do conector Protheus.

O módulo carrega a implementação já existente em `services.py`, preservando a
entrada estável `apps.integrations.protheus.services` pedida pelo merge.
"""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps
from pathlib import Path

from apps.integrations.protheus.client import BaseProtheusClient, HttpProtheusClient, HttpProtheusClientError, build_protheus_client
from apps.integrations.protheus.fake import MemoryProtheusClient


_LEGACY_PATH = Path(__file__).resolve().parents[1] / "services.py"
_LEGACY_SPEC = spec_from_file_location("apps.integrations.protheus._legacy_services", _LEGACY_PATH)
_LEGACY = module_from_spec(_LEGACY_SPEC)
assert _LEGACY_SPEC and _LEGACY_SPEC.loader
_LEGACY_SPEC.loader.exec_module(_LEGACY)

get_enabled_config = _LEGACY.get_enabled_config
serialize_work_order = _LEGACY.serialize_work_order
serialize_material = _LEGACY.serialize_material
serialize_supplier = _LEGACY.serialize_supplier
enqueue_work_order_export = _LEGACY.enqueue_work_order_export
enqueue_material_export = _LEGACY.enqueue_material_export
enqueue_supplier_export = _LEGACY.enqueue_supplier_export
maybe_enqueue_work_order_export = _LEGACY.maybe_enqueue_work_order_export
enqueue_sync_run_async = _LEGACY.enqueue_sync_run_async
process_sync_run = _LEGACY.process_sync_run
import_materials = _LEGACY.import_materials
import_suppliers = _LEGACY.import_suppliers
import_work_orders = _LEGACY.import_work_orders
apply_catalog_staging = _LEGACY.apply_catalog_staging
reject_catalog_staging = _LEGACY.reject_catalog_staging
stage_materials = _LEGACY.stage_materials
stage_suppliers = _LEGACY.stage_suppliers
pull_from_client = _LEGACY.pull_from_client


def canonical_json(data):
    return dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def payload_digest(data):
    return sha256(canonical_json(data).encode("utf-8")).hexdigest()


def extract_remote_code(payload):
    return payload.get("remote_code") or payload.get("code") or payload.get("number")


def build_entity_payload(entity_type, source, price=None):
    if entity_type in {"of", "work_order"}:
        return serialize_work_order(source)
    if entity_type == "material":
        return serialize_material(source, price=price)
    if entity_type == "supplier":
        return serialize_supplier(source)
    if entity_type == "bom":
        payload = serialize_work_order(source)
        remote_code = f"BOM-{payload['number']}"
        return {
            "entity_type": "bom",
            "remote_code": remote_code,
            "code": remote_code,
            "items": payload.get("items", []),
            "source_work_order": payload,
        }
    raise ValueError(f"unsupported entity_type={entity_type!r}")


export_payload = build_entity_payload
import_payload = pull_from_client

__all__ = [
    "BaseProtheusClient",
    "HttpProtheusClient",
    "HttpProtheusClientError",
    "build_protheus_client",
    "apply_catalog_staging",
    "MemoryProtheusClient",
    "build_entity_payload",
    "canonical_json",
    "enqueue_material_export",
    "enqueue_supplier_export",
    "enqueue_sync_run_async",
    "enqueue_work_order_export",
    "extract_remote_code",
    "export_payload",
    "get_enabled_config",
    "import_materials",
    "import_payload",
    "import_suppliers",
    "import_work_orders",
    "maybe_enqueue_work_order_export",
    "payload_digest",
    "process_sync_run",
    "reject_catalog_staging",
    "pull_from_client",
    "serialize_material",
    "serialize_supplier",
    "serialize_work_order",
    "stage_materials",
    "stage_suppliers",
]
