from django.urls import path
from apps.production import views

app_name = "production"

urlpatterns = [
    path("ofs/", views.list_ordens, name="list"),
    path("ofs/<int:pk>/", views.ordem_detail, name="detail"),
    path("ofs/<int:pk>/transicao/", views.transition_ordem, name="transition"),
    path("ofs/<int:pk>/itp/gerar/", views.generate_itp, name="generate_itp"),
    path("cotacoes/<int:quotation_pk>/converter-of/", views.convert_quotation, name="convert"),
    path("ofs/operacao/<int:op_pk>/apontar/", views.appoint, name="appoint"),
    path("ofs/itp/<int:item_pk>/aceitar/", views.accept_itp_item, name="accept_itp_item"),
]
