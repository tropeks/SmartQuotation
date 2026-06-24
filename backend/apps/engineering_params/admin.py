from django.contrib import admin

from apps.engineering_params.models import ProcessParameter, Rate, TenantParamConfig


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = ("operacao", "rate_hh", "rate_hm", "valid_from", "valid_until")
    list_filter = ("operacao", "valid_from")
    search_fields = ("operacao",)
    ordering = ("operacao", "-valid_from")


@admin.register(ProcessParameter)
class ProcessParameterAdmin(admin.ModelAdmin):
    list_display = ("operacao", "metodo", "material", "valor", "unidade", "valid_from", "valid_until")
    list_filter = ("metodo", "unidade", "material", "operacao", "valid_from")
    search_fields = ("operacao", "material", "descricao")
    ordering = ("operacao", "metodo", "material", "-valid_from")


@admin.register(TenantParamConfig)
class TenantParamConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "fator_correcao_mo", "drill_method_threshold_holes", "updated_at")
