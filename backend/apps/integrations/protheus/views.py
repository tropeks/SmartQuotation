from django.http import JsonResponse

from apps.integrations.protheus import services


def admin_healthcheck(_request):
    summary = services.run_healthcheck()
    status = 503 if summary.get("enabled") and not summary.get("ok") else 200
    return JsonResponse(summary, status=status)
