"""URLs do schema de TENANT (app por subdomínio)."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),         # login/logout/dashboard
    path("", include("apps.quotations.urls")),       # cotações + data sheet do feixe
    path("", include("apps.proposals.urls")),        # propostas DOCX/PDF
]
