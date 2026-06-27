"""URLs do schema PUBLIC (landing/health, sem dados de tenant)."""
from django.contrib import admin
from django.urls import path

from apps.health.views import HealthCheckView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", HealthCheckView.as_view(), name="health"),
]
