from django.contrib import admin

from apps.integrations.admin_forms import secret_config_form
from apps.integrations.bling.models import BlingIntegrationConfig


@admin.register(BlingIntegrationConfig)
class BlingIntegrationConfigAdmin(admin.ModelAdmin):
    form = secret_config_form(BlingIntegrationConfig, ("client_id", "client_secret", "access_token", "refresh_token"))
    list_display = ("provider", "enabled", "company_id", "token_expires_at")
    list_filter = ("enabled",)
    search_fields = ("company_id",)
    readonly_fields = ("provider", "created_at", "updated_at")
