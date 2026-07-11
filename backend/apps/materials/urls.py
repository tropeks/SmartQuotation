from django.urls import path

from apps.materials import views

app_name = "materials"

urlpatterns = [
    path("materiais/", views.list_materials, name="list"),
]
