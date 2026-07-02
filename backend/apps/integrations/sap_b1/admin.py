from django.contrib import admin
from django.db import connection
from django.urls import reverse
from django.utils.html import format_html

from apps.integrations.sap_b1 import services
from apps.integrations.admin_forms import secret_config_form
from apps.integrations.sap_b1.models import (
    SapB1ExportLog,
    SapB1IntegrationConfig,
    SapB1SyncAttempt,
    SapB1SyncBinding,
    SapB1SyncRun,
)


class SapB1ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = []
        for field in self.model._meta.fields:
            fields.append(field.name)
        return tuple(fields)


@admin.register(SapB1IntegrationConfig)
class SapB1IntegrationConfigAdmin(admin.ModelAdmin):
    form = secret_config_form(SapB1IntegrationConfig, ("password",))
    list_display = (
        "provider",
        "enabled",
        "company_db",
        "sync_sales_orders_enabled",
        "sync_boms_enabled",
        "last_healthcheck_at",
        "healthcheck_link",
    )
    list_filter = ("enabled", "sync_sales_orders_enabled", "sync_boms_enabled")
    search_fields = ("company_db", "base_url", "username")
    readonly_fields = ("provider", "created_at", "updated_at", "last_healthcheck_at")
    actions = ["run_healthcheck"]

    @admin.display(description="Healthcheck")
    def healthcheck_link(self, _obj):
        return format_html('<a href="{}">Ver status</a>', reverse("sap-b1-admin-health"))

    @admin.action(description="Executar healthcheck operacional")
    def run_healthcheck(self, request, queryset):
        checked = 0
        failures = 0
        for config in queryset:
            if not config.enabled:
                continue
            summary = services.run_healthcheck(config=config)
            checked += 1
            if not summary["ok"]:
                failures += 1
        self.message_user(request, f"{checked} configuracao(oes) verificada(s); {failures} com falha remota.")


@admin.register(SapB1SyncBinding)
class SapB1SyncBindingAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "local_model", "local_id", "remote_code", "last_direction")
    list_filter = ("entity_type", "last_direction", "source_of_truth")
    search_fields = ("local_model", "local_id", "remote_code")


class SapB1SyncAttemptInline(admin.TabularInline):
    model = SapB1SyncAttempt
    extra = 0
    can_delete = False


@admin.register(SapB1SyncRun)
class SapB1SyncRunAdmin(SapB1ReadOnlyAdmin):
    list_display = ("direction", "entity_type", "status", "trigger", "local_model", "local_id", "remote_code")
    list_filter = ("direction", "entity_type", "status", "trigger")
    search_fields = ("idempotency_key", "local_model", "local_id", "remote_code")
    inlines = [SapB1SyncAttemptInline]
    actions = ["reenqueue_runs"]

    @admin.action(description="Reenfileirar runs selecionados")
    def reenqueue_runs(self, request, queryset):
        queued = 0
        skipped = 0
        failures = 0
        for run in queryset:
            if not services.reset_sync_run_for_requeue(run):
                skipped += 1
                continue
            ok = services.enqueue_sync_run_async(
                run,
                schema_name=connection.schema_name,
                raise_on_error=False,
            )
            if not ok:
                failures += 1
                continue
            queued += 1
        self.message_user(
            request,
            f"{queued} run(s) reenfileirado(s); {skipped} ignorado(s); {failures} falharam ao publicar task.",
        )


@admin.register(SapB1SyncAttempt)
class SapB1SyncAttemptAdmin(SapB1ReadOnlyAdmin):
    list_display = ("run", "sequence", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("run__idempotency_key", "run__local_id")


@admin.register(SapB1ExportLog)
class SapB1ExportLogAdmin(admin.ModelAdmin):
    list_display = ("sap_doc_entry", "sap_status", "conflict", "last_checked_at", "created_at")
    list_filter = ("sap_status", "conflict")
    search_fields = ("sap_doc_entry",)
    readonly_fields = ("created_at", "updated_at", "last_checked_at")
    actions = ["force_resync"]

    @admin.action(description="Forçar re-sync de export logs selecionados")
    def force_resync(self, request, queryset):
        from django.db import connection
        from apps.integrations.sap_b1.tasks import check_sap_b1_export_status

        schema_name = connection.schema_name
        resynced = 0
        conflicts_cleared = 0
        for log in queryset:
            had_conflict = log.conflict
            log.sap_status = SapB1ExportLog.SAP_STATUS_PENDING
            log.error_message = ""
            log.conflict = False
            log.conflict_reason = ""
            log.save(update_fields=["sap_status", "error_message", "conflict", "conflict_reason", "updated_at"])
            check_sap_b1_export_status.delay(log_id=log.pk, tenant_schema=schema_name)
            resynced += 1
            if had_conflict:
                conflicts_cleared += 1
        msg = f"{resynced} export log(s) reenfileirado(s) para re-sync."
        if conflicts_cleared:
            msg += f" {conflicts_cleared} conflito(s) resolvido(s)."
        self.message_user(request, msg)
