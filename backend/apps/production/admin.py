from importlib import import_module

from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from apps.integrations.bling.tasks import export_of_to_bling as export_of_to_bling_task

from apps.production.models import (
    InspectionItem, InspectionPlan, OrdemFabricacao, OFItem, OFMaterial, OFOperation,
    ProductionObservation,
)


_SAP_B1_SERVICE_MODULE = "apps.integrations.sap_b1.services"


def _load_sap_b1_services():
    try:
        return import_module(_SAP_B1_SERVICE_MODULE)
    except ModuleNotFoundError as exc:
        raise ImproperlyConfigured("apps.integrations.sap_b1.services indisponivel") from exc


def _call_first_available(module, candidates, *args, **kwargs):
    for candidate in candidates:
        fn = getattr(module, candidate, None)
        if callable(fn):
            return fn(*args, **kwargs)
    raise ImproperlyConfigured(
        f"Nenhuma funcao encontrada em {_SAP_B1_SERVICE_MODULE}: {', '.join(candidates)}"
    )


def _normalize_run_result(result):
    if isinstance(result, tuple):
        if not result:
            return None, False
        run = result[0]
        created = bool(result[1]) if len(result) > 1 else False
        return run, created
    # Bare run objects (the dedup-aware maybe_enqueue_* style) carry no created
    # flag, so we don't infer one: the status check decides whether to publish.
    return result, False


def _should_publish_run(run, created):
    if run is None:
        return False
    if created:
        return True
    return getattr(run, "status", None) not in {"pending", "processing", "success"}


@admin.register(OrdemFabricacao)
class OrdemFabricacaoAdmin(admin.ModelAdmin):
    list_display = ("number", "quotation_number", "customer_name", "status", "created_at")
    list_filter = ("status",)
    actions = ["export_to_sap_b1", "export_to_bling"]

    @admin.action(description="Exportar OF selecionadas para Bling (NF-e)")
    def export_to_bling(self, request, queryset):
        schema_name = connection.schema_name
        queued = 0
        for of in queryset:
            export_of_to_bling_task.delay(of.pk, schema_name)
            queued += 1
        self.message_user(
            request,
            f"{queued} OF(s) enfileirada(s) para exportacao Bling.",
            messages.INFO,
        )

    @admin.action(description="Exportar OF selecionadas para SAP B1")
    def export_to_sap_b1(self, request, queryset):
        services = _load_sap_b1_services()
        queued = 0
        skipped = 0
        failures = 0
        for of in queryset:
            runs = []
            sales_order_run = _call_first_available(
                services,
                (
                    "maybe_enqueue_sales_order_sync",
                    "enqueue_sales_order_sync",
                ),
                of,
                trigger="admin",
            )
            sales_order_run, sales_order_created = _normalize_run_result(sales_order_run)
            if _should_publish_run(sales_order_run, sales_order_created):
                runs.append(sales_order_run)

            bom_run = _call_first_available(
                services,
                (
                    "maybe_enqueue_bom_sync",
                    "enqueue_bom_sync",
                ),
                of,
                trigger="admin",
            )
            bom_run, bom_run_created = _normalize_run_result(bom_run)
            if _should_publish_run(bom_run, bom_run_created):
                runs.append(bom_run)

            if not runs:
                skipped += 1
                continue

            for run in runs:
                ok = _call_first_available(
                    services,
                    ("enqueue_sync_run_async",),
                    run,
                    schema_name=connection.schema_name,
                )
                if ok is False:
                    failures += 1
                    continue
                queued += 1
        level = messages.ERROR if failures else messages.INFO
        self.message_user(
            request,
            f"{queued} run(s) SAP B1 enfileirado(s); {skipped} OF(s) ignorada(s); {failures} falharam ao publicar task.",
            level=level,
        )


@admin.register(OFItem)
class OFItemAdmin(admin.ModelAdmin):
    list_display = ("ordem", "codigo_item", "descricao", "custo_material", "custo_mo")


@admin.register(OFMaterial)
class OFMaterialAdmin(admin.ModelAdmin):
    list_display = ("item", "codigo_mp", "descricao", "peso_bruto_kg", "custo")


@admin.register(OFOperation)
class OFOperationAdmin(admin.ModelAdmin):
    list_display = ("item", "codigo_op", "descricao", "custo", "aplicavel")


@admin.register(ProductionObservation)
class ProductionObservationAdmin(admin.ModelAdmin):
    """SQ-COST-4: superfície somente-leitura do desvio horas orçado × real (SQ-COST-3).

    Mesmo padrão de apps.integrations.sap_b1.admin.SapB1ReadOnlyAdmin — bloqueia
    add/delete e expõe todos os campos como readonly; não recalcula nada.
    """
    list_display = (
        "ordem", "operacao", "estimated_hh", "actual_hh", "delta_horas_pct",
        "observed_rate", "observed_at",
    )
    list_filter = ("operacao",)
    search_fields = ("operacao", "ordem__number")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


class InspectionItemInline(admin.TabularInline):
    model = InspectionItem
    extra = 0
    readonly_fields = ("status", "accepted_by", "accepted_at")


@admin.register(InspectionPlan)
class InspectionPlanAdmin(admin.ModelAdmin):
    list_display = ("ordem", "status", "source_operations_count", "generated_at", "completed_at")
    list_filter = ("status",)
    inlines = [InspectionItemInline]


@admin.register(InspectionItem)
class InspectionItemAdmin(admin.ModelAdmin):
    list_display = ("plan", "sequence", "codigo_op", "inspection_type", "status", "accepted_by", "accepted_at")
    list_filter = ("status", "inspection_type")
    readonly_fields = ("status", "accepted_by", "accepted_at")
