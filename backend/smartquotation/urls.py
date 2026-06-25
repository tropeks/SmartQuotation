"""URLs do schema de TENANT (app por subdomínio)."""
from django.contrib import admin
from django.urls import include, path

from apps.integrations.protheus import views as protheus_views

urlpatterns = [
    path("admin/protheus/health/", admin.site.admin_view(protheus_views.admin_healthcheck), name="protheus-admin-health"),
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),         # login/logout/dashboard
    path("", include("apps.quotations.urls")),       # cotações + data sheet do feixe
    path("", include("apps.proposals.urls")),        # propostas DOCX/PDF
    path("", include("apps.production.urls")),       # ordens de fabricação
    path("", include("apps.engineering_params.urls")),  # learning engine: sugestões de rate
    path("", include("apps.cost_discovery.urls")),   # wizard de cadeia de custos
    path("", include("apps.tema_templates.urls")),   # catálogo TEMA + composição
]
