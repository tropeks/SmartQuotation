from django.contrib import admin

from apps.integrations.protheus.models import (
    ProtheusBOMSnapshot,
    ProtheusIntegrationConfig,
    ProtheusSupplier,
    ProtheusSyncAttempt,
    ProtheusSyncBinding,
    ProtheusSyncRun,
    ProtheusWorkOrderSnapshot,
)


@admin.register(ProtheusIntegrationConfig)
class ProtheusIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ("provider", "enabled", "company_code", "branch_code", "export_on_release")


@admin.register(ProtheusSyncBinding)
class ProtheusSyncBindingAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "local_model", "local_id", "remote_code", "last_direction")
    list_filter = ("entity_type", "last_direction", "source_of_truth")
    search_fields = ("local_model", "local_id", "remote_code")


class ProtheusSyncAttemptInline(admin.TabularInline):
    model = ProtheusSyncAttempt
    extra = 0
    can_delete = False


@admin.register(ProtheusSyncRun)
class ProtheusSyncRunAdmin(admin.ModelAdmin):
    list_display = ("direction", "entity_type", "status", "trigger", "local_model", "local_id", "remote_code")
    list_filter = ("direction", "entity_type", "status", "trigger")
    search_fields = ("idempotency_key", "local_model", "local_id", "remote_code")
    inlines = [ProtheusSyncAttemptInline]


@admin.register(ProtheusSupplier)
class ProtheusSupplierAdmin(admin.ModelAdmin):
    list_display = ("supplier_code", "legal_name", "cnpj", "is_active")
    search_fields = ("supplier_code", "legal_name", "cnpj")


@admin.register(ProtheusWorkOrderSnapshot)
class ProtheusWorkOrderSnapshotAdmin(admin.ModelAdmin):
    list_display = ("remote_code", "title", "customer_name", "status", "last_synced_at")
    search_fields = ("remote_code", "title", "customer_name")


@admin.register(ProtheusBOMSnapshot)
class ProtheusBOMSnapshotAdmin(admin.ModelAdmin):
    list_display = ("work_order", "last_synced_at")
