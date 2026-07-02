import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartquotation.settings.development")
app = Celery("smartquotation")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.beat_schedule = {
    "dispatch-recurring-protheus-pulls": {
        "task": "integrations.protheus.dispatch_recurring_pulls",
        "schedule": settings.PROTHEUS_PULL_INTERVAL,
    },
    "check-pending-sap-b1-exports": {
        "task": "integrations.sap_b1.check_pending_exports",
        "schedule": settings.SAP_B1_EXPORT_CHECK_INTERVAL,
    },
}
app.autodiscover_tasks()
