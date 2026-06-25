from django.apps import AppConfig


class OmieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations.omie"
    label = "integrations_omie"
    verbose_name = "Integracoes - Omie"

