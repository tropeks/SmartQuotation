"""Rotas do app accounts (incluídas no URLconf de tenant)."""
from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("members/", views.members_view, name="accounts_members"),
    path("members/invite/", views.invite_member_view, name="accounts_invite_member"),
    path("", views.dashboard_view, name="dashboard"),
]
