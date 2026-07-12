from django.urls import path
from apps.engineering_params import views

app_name = 'engineering_params'

urlpatterns = [
    path('engenharia/calibracao/', views.calibration, name='calibration'),
    path('engenharia/calibracao/rates/<int:pk>/', views.save_rate, name='save_rate'),
    path('engenharia/calibracao/rates/<int:pk>/preview/', views.preview_rate_impact, name='preview_rate_impact'),
    path('engenharia/calibracao/process-parameters/<int:pk>/', views.save_process_parameter, name='save_process_parameter'),
    path('engenharia/calibracao/process-parameters/<int:pk>/preview/', views.preview_process_parameter_impact, name='preview_process_parameter_impact'),
    path('engenharia/calibracao/sugestoes/<int:pk>/aceitar/', views.accept_rate_suggestion, name='accept_rate_suggestion'),
    path('engenharia/sugestoes/', views.suggestions_list, name='suggestions'),
    path('engenharia/sugestoes/<int:pk>/aplicar/', views.suggestion_apply, name='suggestion_apply'),
    path('engenharia/sugestoes/<int:pk>/descartar/', views.suggestion_dismiss, name='suggestion_dismiss'),
]
