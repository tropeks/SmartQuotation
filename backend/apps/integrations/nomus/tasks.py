import logging

from celery import shared_task
from django_tenants.utils import schema_context

from apps.integrations.nomus.client import HttpNomusTransientError
from apps.integrations.nomus.models import NomusSyncRun
from apps.integrations.nomus.services import process_sync_run

logger = logging.getLogger(__name__)


def _build_run_result(run):
    return {
        "run_id": run.pk,
        "status": run.status,
        "direction": run.direction,
        "entity_type": run.entity_type,
    }


def process_sync_run_for_schema(schema_name, run_id):
    with schema_context(schema_name):
        run = NomusSyncRun.objects.get(pk=run_id)
        if run.status == NomusSyncRun.STATUS_SUCCESS:
            return _build_run_result(run)
        processed = process_sync_run(run)
        return _build_run_result(processed)


@shared_task(
    bind=True,
    name="integrations.nomus.process_sync_run",
    autoretry_for=(HttpNomusTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_nomus_sync_run(self, schema_name, run_id):
    return process_sync_run_for_schema(schema_name, run_id)
