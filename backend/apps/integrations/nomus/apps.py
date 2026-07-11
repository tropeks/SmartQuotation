from django.apps import AppConfig


class NomusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations.nomus"
    label = "integrations_nomus"
    verbose_name = "Integracoes - Nomus"

