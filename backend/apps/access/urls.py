"""Rotas do app access (incluídas no URLconf de tenant)."""
from django.urls import path

from apps.access import views

app_name = "access"

urlpatterns = [
    path("config/", views.access_config, name="config"),
    path("config/toggle/", views.toggle_permission, name="toggle_permission"),
    path("config/stage/toggle/", views.toggle_stage, name="toggle_stage"),
    # RBAC V2 M2 — página "Papéis" (papéis como dado), gate role.manage.
    path("config/roles/", views.roles_list, name="roles"),
    path("config/roles/new/", views.role_new, name="role_new"),
    path("config/roles/create/", views.role_create, name="role_create"),
    path("config/roles/<slug:key>/edit/", views.role_edit, name="role_edit"),
    path("config/roles/update/", views.role_update, name="role_update"),
    path("config/roles/delete/", views.role_delete, name="role_delete"),
    # RBAC V2 M3 — builder de fluxo de aprovação, gate access.manage.
    path("config/workflow/", views.workflow_config, name="workflow"),
    path("config/workflow/apply-template/", views.workflow_apply_template, name="workflow_apply_template"),
    path("config/workflow/stage/add/", views.stage_add, name="stage_add"),
    path("config/workflow/stage/edit/", views.stage_edit, name="stage_edit"),
    path("config/workflow/stage/remove/", views.stage_remove, name="stage_remove"),
    path("config/workflow/stage/move/", views.stage_move, name="stage_move"),
]
