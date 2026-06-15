"""Admin do catálogo de materiais e do CADASTRO DE LIGAS (editável sem deploy — #2 Wellington)."""
from django.contrib import admin

from apps.materials.models import Material, MaterialPrice, LigaMetalurgica


@admin.register(LigaMetalurgica)
class LigaMetalurgicaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "familia", "spec", "liga_fator", "preco_fator",
                    "temp_limite_c", "edicao", "is_active", "ordem")
    list_editable = ("liga_fator", "preco_fator", "temp_limite_c", "is_active", "ordem")
    list_filter = ("is_active", "familia", "edicao")
    search_fields = ("codigo", "nome", "spec")
    fieldsets = (
        (None, {"fields": ("codigo", "nome", "familia", "spec", "is_active", "ordem")}),
        ("Tensão admissível", {"fields": ("s_curva",),
         "description": "Curva S em MPa por °C, ex.: {\"40\": 217, \"300\": 205}. "
                        "Acima da maior temperatura → S indisponível (não extrapola)."}),
        ("Fatores de custo", {"fields": ("liga_fator", "densidade_kg_mm3", "preco_fator",
                                         "temp_limite_c")}),
        ("Procedência (rastreabilidade ASME)", {"fields": ("norma", "edicao", "tabela", "linha")}),
    )


admin.site.register(Material)
admin.site.register(MaterialPrice)
