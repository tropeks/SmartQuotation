from django.contrib import admin
from apps.production.models import OrdemFabricacao, OFItem, OFMaterial, OFOperation


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
