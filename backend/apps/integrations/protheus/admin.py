from django.contrib import admin
from django.db import connection

from apps.integrations.protheus.models import (
    ProtheusCatalogStaging,
    ProtheusBOMSnapshot,
    ProtheusIntegrationConfig,
    ProtheusSupplier,
    ProtheusSyncAttempt,
    ProtheusSyncBinding,
    ProtheusSyncRun,
    ProtheusWorkOrderSnapshot,
)
from apps.integrations.protheus import services


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
    actions = ["reenqueue_runs"]

    @admin.action(description="Reenfileirar runs selecionados")
    def reenqueue_runs(self, request, queryset):
        queued = 0
        for run in queryset:
            run.status = ProtheusSyncRun.STATUS_PENDING
            run.error_message = ""
            run.finished_at = None
            run.result_payload = {}
            run.save(update_fields=["status", "error_message", "finished_at", "result_payload"])
            services.enqueue_sync_run_async(run, schema_name=connection.schema_name)
            queued += 1
        self.message_user(request, f"{queued} run(s) reenfileirado(s).")


@admin.register(ProtheusCatalogStaging)
class ProtheusCatalogStagingAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "remote_code", "status", "source_run", "applied_object_model", "created_at")
    list_filter = ("entity_type", "status")
    search_fields = ("remote_code", "payload_hash", "applied_object_model")
    actions = ["apply_staging", "reject_staging"]

    @admin.action(description="Aplicar staging selecionado")
    def apply_staging(self, request, queryset):
        applied = 0
        for staging in queryset:
            services.apply_catalog_staging(staging, actor=request.user)
            applied += 1
        self.message_user(request, f"{applied} staging item(ns) aplicado(s).")

    @admin.action(description="Rejeitar staging selecionado")
    def reject_staging(self, request, queryset):
        rejected = 0
        for staging in queryset:
            services.reject_catalog_staging(staging, actor=request.user, reason="Rejeitado via admin")
            rejected += 1
        self.message_user(request, f"{rejected} staging item(ns) rejeitado(s).")


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
