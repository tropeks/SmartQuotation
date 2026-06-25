from celery import shared_task
from django_tenants.utils import schema_context

from apps.integrations.omie.client import HttpOmieTransientError
from apps.integrations.omie.models import OmieInvoiceRun
from apps.integrations.omie.services import process_invoice_run as process_invoice_run_service


def _build_run_result(run):
    return {
        "run_id": run.pk,
        "status": run.status,
        "document_id": run.document_id,
        "remote_document_id": run.document.remote_document_id if getattr(run, "document_id", None) else None,
        "remote_number": run.document.remote_number if getattr(run, "document_id", None) else None,
    }


def process_invoice_run_for_schema(schema_name, run_id):
    with schema_context(schema_name):
        run = OmieInvoiceRun.objects.select_related("config", "document").get(pk=run_id)
        if run.status == OmieInvoiceRun.STATUS_SUCCESS:
            return _build_run_result(run)
        processed = process_invoice_run_service(run)
        return _build_run_result(processed)


@shared_task(
    bind=True,
    name="integrations.omie.process_invoice_run",
    autoretry_for=(HttpOmieTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_omie_invoice_run(self, schema_name, run_id):
    return process_invoice_run_for_schema(schema_name, run_id)


process_invoice_run = process_omie_invoice_run
