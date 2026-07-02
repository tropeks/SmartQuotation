from django.apps import AppConfig


class SAPB1Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations.sap_b1"
    label = "integrations_sap_b1"
    verbose_name = "Integracoes - SAP B1"

    def ready(self):
        from django.db.models.signals import pre_save, post_save
        from apps.production.models import OrdemFabricacao
        from apps.integrations.sap_b1 import services

        pre_save.connect(
            services._on_of_pre_save,
            sender=OrdemFabricacao,
            dispatch_uid="sap_b1_of_pre_save",
        )
        post_save.connect(
            services._on_of_post_save,
            sender=OrdemFabricacao,
            dispatch_uid="sap_b1_of_post_save",
        )
