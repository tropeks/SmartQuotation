from django.urls import path
from apps.cost_discovery import views

app_name = "cost_discovery"

urlpatterns = [
    path("custos/", views.wizard_home, name="home"),
    path("custos/seed/", views.top_down, name="top_down"),
    path("custos/calibrar/", views.back_solve, name="back_solve"),
]
