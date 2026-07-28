from django.contrib import admin

from apps.cost_structure.models import CostStructure


@admin.register(CostStructure)
class CostStructureAdmin(admin.ModelAdmin):
    list_display = ("valid_from", "valid_until", "empresa", "custo_mensal",
                    "horas_mes", "custo_hora", "rate_praticado", "origem")
    list_filter = ("origem",)
    readonly_fields = ("payload", "created_at")
