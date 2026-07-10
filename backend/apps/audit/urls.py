from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("cotacoes/<int:pk>/aprovacoes/remoto/", views.request_remote, name="request_remote"),
    path("cotacoes/<int:pk>/aprovacoes/presencial/", views.approve_presencial_view, name="approve_presencial"),
    path("cotacoes/<int:pk>/aprovacoes/convertibility-panel/", views.convertibility_panel, name="convertibility_panel"),
]
