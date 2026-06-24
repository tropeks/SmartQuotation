from django.contrib import admin
from apps.production.models import (
    InspectionItem, InspectionPlan, OrdemFabricacao, OFItem, OFMaterial, OFOperation,
)


@admin.register(OrdemFabricacao)
class OrdemFabricacaoAdmin(admin.ModelAdmin):
    list_display = ("number", "quotation_number", "customer_name", "status", "created_at")
    list_filter = ("status",)


@admin.register(OFItem)
class OFItemAdmin(admin.ModelAdmin):
    list_display = ("ordem", "codigo_item", "descricao", "custo_material", "custo_mo")


@admin.register(OFMaterial)
class OFMaterialAdmin(admin.ModelAdmin):
    list_display = ("item", "codigo_mp", "descricao", "peso_bruto_kg", "custo")


@admin.register(OFOperation)
class OFOperationAdmin(admin.ModelAdmin):
    list_display = ("item", "codigo_op", "descricao", "custo", "aplicavel")


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
