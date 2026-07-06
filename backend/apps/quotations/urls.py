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
    path("cotacoes/recompute/", views.recompute_preview, name="recompute"),
    path("cotacoes/criar/", views.create_quotation, name="create"),
    path("cotacoes/<int:pk>/", views.quotation_detail, name="detail"),
    path("cotacoes/<int:pk>/editar/", views.quotation_edit, name="edit"),
    path("cotacoes/<int:pk>/revisar/", views.quotation_revise, name="revise"),
    # API endpoints (DRF)
    path("api/", include(router.urls)),
    path("api/permutador/estimate/", api.PermutadorEstimateView.as_view(), name="api_permutador_estimate"),
]
