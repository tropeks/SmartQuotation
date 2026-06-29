from django.contrib import admin, messages

from apps.integrations.admin_forms import secret_config_form
from apps.integrations.bling.models import BlingIntegrationConfig
from apps.integrations.bling.client import BlingClient, BlingClientError


@admin.register(BlingIntegrationConfig)
class BlingIntegrationConfigAdmin(admin.ModelAdmin):
    form = secret_config_form(BlingIntegrationConfig, ("client_id", "client_secret", "access_token", "refresh_token"))
    list_display = ("provider", "enabled", "company_id", "token_expires_at")
    list_filter = ("enabled",)
    search_fields = ("company_id",)
    readonly_fields = (
        "provider",
        "created_at",
        "updated_at",
        "client_id",
        "client_secret",
        "access_token",
        "refresh_token",
    )
    actions = ("check_health",)

    def check_health(self, request, queryset):
        for config in queryset:
            try:
                client = BlingClient(config)
                client.ping()
                self.message_user(
                    request,
                    f"✓ Conexão com Bling sucesso para {config.company_id}",
                    messages.SUCCESS,
                )
            except BlingClientError as e:
                self.message_user(
                    request,
                    f"✗ Erro ao conectar com Bling para {config.company_id}: {e}",
                    messages.ERROR,
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"✗ Erro inesperado ao verificar saúde de {config.company_id}: {e}",
                    messages.ERROR,
                )

    check_health.short_description = "Verificar conexão com Bling (ping)"
