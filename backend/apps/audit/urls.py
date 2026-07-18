from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("cotacoes/<int:pk>/aprovacoes/remoto/", views.request_remote, name="request_remote"),
    path("cotacoes/<int:pk>/aprovacoes/presencial/", views.approve_presencial_view, name="approve_presencial"),
    path("cotacoes/<int:pk>/aprovacoes/convertibility-panel/", views.convertibility_panel, name="convertibility_panel"),
    # RBAC V2 M5 — inbox de aprovações + badge.
    path("cotacoes/<int:pk>/aprovacoes/solicitar/", views.request_approval, name="request_approval"),
    path("aprovacoes/", views.inbox, name="inbox"),
    path("aprovacoes/badge/", views.inbox_badge, name="inbox_badge"),
    path("aprovacoes/task/<int:task_id>/aprovar/", views.approve_task, name="approve_task"),
    path("aprovacoes/task/<int:task_id>/rejeitar/", views.reject_task, name="reject_task"),
]
