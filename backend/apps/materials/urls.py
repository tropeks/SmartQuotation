from django.urls import path

from apps.materials import views

app_name = "materials"

urlpatterns = [
    path("materiais/", views.list_materials, name="list"),
    path("materiais/<int:pk>/", views.detail_material, name="detail"),
    path("materiais/<int:pk>/precos/<str:forma>/", views.save_material_price, name="save_price"),
]
