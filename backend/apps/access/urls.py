"""Rotas do app access (incluídas no URLconf de tenant)."""
from django.urls import path

from apps.access import views

app_name = "access"

urlpatterns = [
    path("config/", views.access_config, name="config"),
    path("config/toggle/", views.toggle_permission, name="toggle_permission"),
]
