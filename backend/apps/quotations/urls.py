from django.urls import path
from apps.quotations import views

app_name = "quotations"

urlpatterns = [
    path("cotacoes/", views.list_quotations, name="list"),
    path("cotacoes/nova/feixe/", views.feixe_data_sheet, name="feixe_new"),
    path("cotacoes/recompute/", views.recompute_preview, name="recompute"),
    path("cotacoes/criar/", views.create_quotation, name="create"),
    path("cotacoes/<int:pk>/", views.quotation_detail, name="detail"),
    path("cotacoes/<int:pk>/revisar/", views.quotation_revise, name="revise"),
]
