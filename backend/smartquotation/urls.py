"""URLs do schema de TENANT (app por subdomínio)."""
from importlib import import_module

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.integrations.omie import views as omie_views
from apps.integrations.protheus import views as protheus_views


def _sap_b1_admin_healthcheck(request):
    try:
        sap_b1_views = import_module("apps.integrations.sap_b1.views")
    except ModuleNotFoundError:
        return JsonResponse(
            {"enabled": False, "ok": False, "error": "sap_b1 app indisponivel"},
            status=503,
        )
    return sap_b1_views.admin_healthcheck(request)


urlpatterns = [
    path("admin/protheus/health/", admin.site.admin_view(protheus_views.admin_healthcheck), name="protheus-admin-health"),
    path("admin/omie/health/", admin.site.admin_view(omie_views.admin_healthcheck), name="omie-admin-health"),
    path("admin/sap-b1/health/", admin.site.admin_view(_sap_b1_admin_healthcheck), name="sap-b1-admin-health"),
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),         # login/logout/dashboard
    path("", include("apps.quotations.urls")),       # cotações + data sheet do feixe
    path("", include("apps.proposals.urls")),        # propostas DOCX/PDF
    path("", include("apps.production.urls")),       # ordens de fabricação
    path("", include("apps.engineering_params.urls")),  # learning engine: sugestões de rate
    path("", include("apps.cost_discovery.urls")),   # wizard de cadeia de custos
    path("", include("apps.tema_templates.urls")),   # catálogo TEMA + composição
]
