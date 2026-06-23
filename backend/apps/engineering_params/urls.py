from django.urls import path
from apps.engineering_params import views

app_name = 'engineering_params'

urlpatterns = [
    path('engenharia/sugestoes/', views.suggestions_list, name='suggestions'),
    path('engenharia/sugestoes/<int:pk>/aplicar/', views.suggestion_apply, name='suggestion_apply'),
    path('engenharia/sugestoes/<int:pk>/descartar/', views.suggestion_dismiss, name='suggestion_dismiss'),
]
