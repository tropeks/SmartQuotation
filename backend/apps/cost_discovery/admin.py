from django.contrib import admin
from apps.cost_discovery.models import CostDiscoverySession


@admin.register(CostDiscoverySession)
class CostDiscoverySessionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "method", "solved_fator_mo", "achieved_price", "error_pct")
    list_filter = ("method",)
    readonly_fields = ("solved_fator_mo", "achieved_price", "error_pct", "created_at")
