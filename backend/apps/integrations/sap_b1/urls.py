from django.urls import path

from apps.integrations.sap_b1 import views


urlpatterns = [
    path("admin/sap-b1/health/", views.admin_healthcheck, name="sap-b1-admin-health"),
]

