from django.apps import AppConfig


class ProtheusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations.protheus"
    label = "integrations_protheus"
    verbose_name = "Integracoes - TOTVS Protheus"
