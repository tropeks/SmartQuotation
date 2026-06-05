from django.urls import path
from apps.tema_templates import views

app_name = "tema_templates"

urlpatterns = [
    path("tema/catalogo/", views.catalog, name="catalog"),
    path("tema/compor/", views.compose, name="compose"),
    path("tema/compor/check/", views.compose_check, name="compose_check"),
]
