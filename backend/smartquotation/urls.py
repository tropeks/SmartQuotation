"""URLs do schema de TENANT (app por subdomínio)."""
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
    # apps de domínio adicionam suas rotas conforme construídos
]
