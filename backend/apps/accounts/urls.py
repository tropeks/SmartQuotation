"""Rotas do app accounts (incluídas no URLconf de tenant)."""
from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("members/", views.members_view, name="accounts_members"),
    path("members/invite/", views.invite_member_view, name="accounts_invite_member"),
    path("members/<int:pk>/role/", views.change_member_role_view, name="accounts_change_member_role"),
    path("members/<int:pk>/deactivate/", views.deactivate_member_view, name="accounts_deactivate_member"),
    path("", views.dashboard_view, name="dashboard"),
]
