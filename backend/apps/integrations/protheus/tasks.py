from zlib import crc32

from celery import shared_task
from django.db import connection
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.integrations.protheus.client import HttpProtheusTransientError, build_protheus_client
from apps.integrations.protheus.models import ProtheusSyncRun
from apps.integrations.protheus.services import get_enabled_config, process_sync_run, pull_from_client


_PROTHEUS_PULL_LOCK_CLASS = 251025


def _build_run_result(run):
    return {
        "run_id": run.pk,
        "status": run.status,
        "direction": run.direction,
        "entity_type": run.entity_type,
        "remote_code": run.remote_code,
    }


def _schema_pull_lock_key(schema_name):
    return crc32(schema_name.encode("utf-8")) & 0x7FFFFFFF


def _acquire_schema_pull_lock(schema_name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            [_PROTHEUS_PULL_LOCK_CLASS, _schema_pull_lock_key(schema_name)],
        )
        return bool(cursor.fetchone()[0])


def _release_schema_pull_lock(schema_name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock(%s, %s)",
            [_PROTHEUS_PULL_LOCK_CLASS, _schema_pull_lock_key(schema_name)],
        )
        return bool(cursor.fetchone()[0])


def process_sync_run_for_schema(schema_name, run_id):
    with schema_context(schema_name):
        run = ProtheusSyncRun.objects.get(pk=run_id)
        config = get_enabled_config()
        if config is None or not config.enabled:
            run.status = ProtheusSyncRun.STATUS_SKIPPED
            run.error_message = "Protheus integration is disabled"
            run.finished_at = timezone.now()
            run.result_payload = {"status": "skipped"}
            run.save(update_fields=["status", "error_message", "finished_at", "result_payload"])
            return _build_run_result(run)
        client = build_protheus_client(config=config)
        try:
            processed = process_sync_run(run, client=client)
            return _build_run_result(processed)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def pull_catalog_for_schema(schema_name, entities=None):
    with schema_context(schema_name):
        config = get_enabled_config()
        if config is None or not config.enabled:
            return {"status": "skipped", "suppliers": 0, "materials": 0, "work_orders": 0}
        if not _acquire_schema_pull_lock(schema_name):
            return {
                "status": "skipped",
                "reason": "pull_already_running",
                "suppliers": 0,
                "materials": 0,
                "work_orders": 0,
            }

        client = build_protheus_client(config=config)
        try:
            if entities:
                enabled = set(entities)
                config.pull_suppliers_enabled = config.pull_suppliers_enabled and "suppliers" in enabled
                config.pull_materials_enabled = config.pull_materials_enabled and "materials" in enabled
                config.pull_work_orders_enabled = config.pull_work_orders_enabled and "work_orders" in enabled
            imported = pull_from_client(client, config=config)
            return {
                "status": "success",
                "suppliers": len(imported["suppliers"]),
                "materials": len(imported["materials"]),
                "work_orders": len(imported["work_orders"]),
            }
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
            _release_schema_pull_lock(schema_name)


@shared_task(
    bind=True,
    name="integrations.protheus.process_sync_run",
    autoretry_for=(HttpProtheusTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_protheus_sync_run(self, schema_name, run_id):
    return process_sync_run_for_schema(schema_name, run_id)


@shared_task(
    bind=True,
    name="integrations.protheus.pull_catalog",
    autoretry_for=(HttpProtheusTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def pull_protheus_catalog(self, schema_name, entities=None):
    return pull_catalog_for_schema(schema_name, entities=entities)


@shared_task(name="integrations.protheus.dispatch_recurring_pulls")
def dispatch_recurring_protheus_pulls():
    tenant_model = get_tenant_model()
    dispatched = []
    for tenant in tenant_model.objects.filter(is_active=True).order_by("schema_name"):
        with schema_context(tenant.schema_name):
            config = get_enabled_config()
            if config is None or not config.enabled:
                continue
        pull_protheus_catalog.delay(schema_name=tenant.schema_name)
        dispatched.append(tenant.schema_name)
    return {"status": "success", "dispatched": len(dispatched), "schemas": dispatched}
