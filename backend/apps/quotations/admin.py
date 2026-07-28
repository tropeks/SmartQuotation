"""Admin do app quotations. Foco: compor cotação por PARTES (QuotationPart)."""
from django.contrib import admin

from apps.quotations.models import Quotation, QuotationPart


class QuotationPartInline(admin.TabularInline):
    model = QuotationPart
    extra = 0
    fields = ("sort_order", "template", "tema_letter", "material_sigla", "incluso", "params")


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "scope", "status", "pricing_basis", "custo_total")
    list_filter = ("scope", "status", "pricing_basis")
    search_fields = ("number", "title")
    # Custo, preço e peso são DERIVADOS — saem do motor ou do roll-up da EAP, nunca da
    # digitação. Gravar por aqui não emite CalculationSnapshot, então burlava o selo que
    # amarra a assinatura técnica ao número: os mesmos campos alimentam o cabeçalho da
    # Ordem de Fabricação. Não era escalada de papel (exige is_staff, que nenhum papel de
    # tenant concede), mas era o último bypass conhecido do selo — e nada na tela avisava
    # que o campo era derivado.
    #
    # `pricing_basis` já era read-only (SQ-COST-1 §5.2): rótulo de proveniência, não campo.
    readonly_fields = (
        "pricing_basis",
        "custo_material", "custo_mo", "custo_total",
        "preco_sem_impostos", "preco_com_impostos",
        "peso_bruto_kg", "peso_liquido_kg",
        "fator_preco", "impostos_pct",
        "computed_at",
    )
    inlines = [QuotationPartInline]


@admin.register(QuotationPart)
class QuotationPartAdmin(admin.ModelAdmin):
    list_display = ("quotation", "template", "tema_letter", "material_sigla", "incluso", "sort_order")
    list_filter = ("incluso",)
