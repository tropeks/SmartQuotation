import logging

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.integrations.sap_b1.client import HttpSapB1PermanentError, HttpSapB1TransientError, build_sap_b1_client
from apps.integrations.sap_b1.models import SapB1ExportLog, SapB1SyncRun
from apps.integrations.sap_b1.services import process_sync_run

logger = logging.getLogger(__name__)


def _build_run_result(run):
    return {
        "run_id": run.pk,
        "status": run.status,
        "direction": run.direction,
        "entity_type": run.entity_type,
        "remote_code": run.remote_code,
    }


def process_sync_run_for_schema(schema_name, run_id):
    with schema_context(schema_name):
        run = SapB1SyncRun.objects.get(pk=run_id)
        if run.status == SapB1SyncRun.STATUS_SUCCESS:
            return _build_run_result(run)
        processed = process_sync_run(run)
        return _build_run_result(processed)


@shared_task(
    bind=True,
    name="integrations.sap_b1.process_sync_run",
    autoretry_for=(HttpSapB1TransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_sap_b1_sync_run(self, schema_name, run_id):
    return process_sync_run_for_schema(schema_name, run_id)


@shared_task(
    bind=True,
    name="integrations.sap_b1.export_of_to_sap_b1",
    autoretry_for=(HttpSapB1TransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def export_of_to_sap_b1(self, schema_name, of_id):
    from apps.production.models import OrdemFabricacao
    from apps.integrations.sap_b1 import services

    with schema_context(schema_name):
        of = OrdemFabricacao.objects.get(pk=of_id)
        run, _ = services.enqueue_sales_order_sync(of, trigger="auto_export")
        if run.status == SapB1SyncRun.STATUS_SUCCESS:
            return _build_run_result(run)
        processed = process_sync_run(run)
        return _build_run_result(processed)


@shared_task(
    bind=True,
    name="integrations.sap_b1.check_export_status",
    autoretry_for=(HttpSapB1TransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def check_sap_b1_export_status(self, log_id, tenant_schema):
    with schema_context(tenant_schema):
        log = SapB1ExportLog.objects.get(pk=log_id)
        client = build_sap_b1_client()
        try:
            result = client.get_sales_order_status(log.sap_doc_entry)
            now = timezone.now()
            if result.get("DocumentStatus") == "bost_Close":
                log.sap_status = SapB1ExportLog.SAP_STATUS_SYNCED
            log.last_checked_at = now
            log.error_message = ""
            log.save(update_fields=["sap_status", "last_checked_at", "error_message", "updated_at"])
        except HttpSapB1TransientError:
            raise
        except HttpSapB1PermanentError as exc:
            log.sap_status = SapB1ExportLog.SAP_STATUS_ERROR
            log.last_checked_at = timezone.now()
            log.error_message = str(exc)
            log.save(update_fields=["sap_status", "last_checked_at", "error_message", "updated_at"])


@shared_task(name="integrations.sap_b1.check_pending_exports")
def check_pending_sap_b1_exports():
    from apps.integrations.sap_b1.services import get_enabled_config

    tenant_model = get_tenant_model()
    dispatched = 0
    for tenant in tenant_model.objects.filter(is_active=True).order_by("schema_name"):
        with schema_context(tenant.schema_name):
            config = get_enabled_config()
            if config is None or not config.enabled:
                continue
            pending = list(
                SapB1ExportLog.objects.filter(sap_status=SapB1ExportLog.SAP_STATUS_PENDING).values_list("pk", flat=True)
            )
        for log_id in pending:
            check_sap_b1_export_status.delay(log_id=log_id, tenant_schema=tenant.schema_name)
            dispatched += 1
    return {"status": "success", "dispatched": dispatched}


