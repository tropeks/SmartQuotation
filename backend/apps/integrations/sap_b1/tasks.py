from celery import shared_task
from django_tenants.utils import schema_context

from apps.integrations.sap_b1.client import HttpSapB1TransientError
from apps.integrations.sap_b1.models import SapB1SyncRun
from apps.integrations.sap_b1.services import process_sync_run


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


