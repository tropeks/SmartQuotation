from django.urls import path
from apps.production import views

app_name = "production"

urlpatterns = [
    path("ofs/", views.list_ordens, name="list"),
    path("ofs/<int:pk>/", views.ordem_detail, name="detail"),
    path("ofs/<int:pk>/transicao/", views.transition_ordem, name="transition"),
    path("cotacoes/<int:quotation_pk>/converter-of/", views.convert_quotation, name="convert"),
]
