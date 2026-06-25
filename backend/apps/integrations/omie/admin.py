from django.contrib import admin
from django.db import connection
from django.urls import reverse
from django.utils.html import format_html

from apps.integrations.omie import services
from apps.integrations.omie.models import (
    OmieFiscalDocument,
    OmieIntegrationConfig,
    OmieInvoiceAttempt,
    OmieInvoiceRun,
)


class OmieInvoiceAttemptInline(admin.TabularInline):
    model = OmieInvoiceAttempt
    extra = 0
    can_delete = False
    fields = ("sequence", "status", "created_at")
    readonly_fields = fields


@admin.register(OmieIntegrationConfig)
class OmieIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "enabled",
        "company_code",
        "environment",
        "emit_on_of_completed",
        "last_healthcheck_at",
        "healthcheck_link",
    )
    list_filter = ("enabled", "environment", "emit_on_of_completed")
    search_fields = ("company_code", "environment")
    readonly_fields = ("created_at", "updated_at", "last_healthcheck_at")
    actions = ["run_healthcheck"]

    @admin.display(description="Healthcheck")
    def healthcheck_link(self, _obj):
        return format_html('<a href="{}">Ver status</a>', reverse("omie-admin-health"))

    @admin.action(description="Executar healthcheck operacional")
    def run_healthcheck(self, request, queryset):
        checked = 0
        failures = 0
        for config in queryset:
            if not config.enabled:
                continue
            summary = services.run_healthcheck()
            checked += 1
            if not summary["ok"]:
                failures += 1
        self.message_user(request, f"{checked} configuracao(oes) verificada(s); {failures} com falha remota.")


@admin.register(OmieFiscalDocument)
class OmieFiscalDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "of",
        "config",
        "status",
        "remote_number",
        "prepared_at",
        "issued_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("remote_document_id", "remote_number", "of__number")
    readonly_fields = ("created_at", "updated_at")
    actions = ["issue_documents"]

    @admin.action(description="Emitir NF-e para documentos selecionados")
    def issue_documents(self, request, queryset):
        queued = 0
        for document in queryset.select_related("of"):
            run = services.maybe_enqueue_nfe_issue(document.of, trigger="admin")
            if run is None:
                continue
            services.enqueue_invoice_run_async(run, schema_name=connection.schema_name)
            queued += 1
        self.message_user(request, f"{queued} documento(s) enfileirado(s) para emissão.")


@admin.register(OmieInvoiceRun)
class OmieInvoiceRunAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "status",
        "trigger",
        "idempotency_key",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "trigger")
    search_fields = ("idempotency_key", "document__of__number", "document__remote_number")
    inlines = [OmieInvoiceAttemptInline]
    readonly_fields = ("started_at", "finished_at", "correlation_id")
    actions = ["reenqueue_runs"]

    @admin.action(description="Reenfileirar runs selecionados")
    def reenqueue_runs(self, request, queryset):
        queued = 0
        skipped = 0
        for run in queryset:
            if not services.reset_invoice_run_for_requeue(run):
                skipped += 1
                continue
            services.enqueue_invoice_run_async(run, schema_name=connection.schema_name)
            queued += 1
        self.message_user(request, f"{queued} run(s) reenfileirado(s); {skipped} ignorado(s).")


@admin.register(OmieInvoiceAttempt)
class OmieInvoiceAttemptAdmin(admin.ModelAdmin):
    list_display = ("run", "sequence", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("run__idempotency_key", "run__document__of__number")
    readonly_fields = ("created_at",)
