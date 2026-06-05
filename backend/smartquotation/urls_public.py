"""URLs do schema PUBLIC (landing/health, sem dados de tenant)."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(_request):
    return JsonResponse({"status": "ok", "service": "smartquotation"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
]
