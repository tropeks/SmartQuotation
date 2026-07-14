from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.quotations import views
from apps.quotations import api

app_name = "quotations"

router = DefaultRouter()
router.register(r'cotacoes', api.QuotationViewSet, basename='api_cotacoes')

urlpatterns = [
    path("cotacoes/", views.list_quotations, name="list"),
    path("cotacoes/nova/", views.quotation_new, name="new"),
    path("cotacoes/clientes/criar/", views.customer_quick_create, name="customer_quick_create"),
    path("cotacoes/nova/feixe/", views.feixe_data_sheet, name="feixe_new"),
    path("cotacoes/nova/partes/", views.compose_parts_new, name="parts_new"),
    path("cotacoes/nova/partes/criar/", views.compose_parts_create, name="parts_create"),
    path("cotacoes/partes/compat/", views.compose_compat_check, name="compat_check"),
    path("cotacoes/recompute/", views.recompute_preview, name="recompute"),
    path("cotacoes/criar/", views.create_quotation, name="create"),
    path("cotacoes/<int:pk>/", views.quotation_detail, name="detail"),
    path("cotacoes/<int:pk>/databook/", views.databook_detail, name="databook"),
    path("cotacoes/<int:pk>/databook.csv", views.databook_export, name="databook_export"),
    path("cotacoes/eap/item/<int:pk>/drawer/", views.eap_item_drawer, name="eap_item_drawer"),
    path("cotacoes/eap/item/<int:pk>/salvar/", views.eap_item_save, name="eap_item_save"),
    path("cotacoes/eap/op/<int:pk>/restaurar/", views.eap_op_restore, name="eap_op_restore"),
    path("cotacoes/<int:pk>/status/", views.quotation_set_status, name="set_status"),
    path("cotacoes/<int:pk>/editar/", views.quotation_edit, name="edit"),
    path("cotacoes/<int:pk>/revisar/", views.quotation_revise, name="revise"),
    path("cotacoes/<int:pk>/meta/", views.quotation_update_meta, name="update_meta"),
    # API endpoints (DRF)
    path("api/", include(router.urls)),
    path("api/permutador/estimate/", api.PermutadorEstimateView.as_view(), name="api_permutador_estimate"),
]
