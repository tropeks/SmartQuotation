from django.urls import path

from apps.integrations.nomus import views

app_name = "nomus"

urlpatterns = [
    path("ofs/<int:of_pk>/nomus/painel/", views.export_panel, name="export_panel"),
    path("ofs/<int:of_pk>/nomus/reexport/", views.reexport, name="reexport"),
]
