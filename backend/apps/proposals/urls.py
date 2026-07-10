from django.urls import path
from apps.proposals import views

app_name = "proposals"

urlpatterns = [
    path("cotacoes/<int:quotation_pk>/proposta/nova/", views.proposal_create, name="create"),
    path("propostas/<int:pk>/editar/", views.proposal_edit, name="edit"),
    path("propostas/<int:pk>/", views.proposal_detail, name="detail"),
    path("propostas/<int:pk>/enviar-email/", views.proposal_send_email, name="send_email"),
    path("propostas/<int:pk>/download/<str:fmt>/", views.proposal_download, name="download"),
    path("propostas/<int:pk>/preview/", views.proposal_preview, name="preview"),
]
