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
    # pricing_basis é derivado/read-only (SQ-COST-1 §5.2): não deve virar campo editável à
    # mão no admin, só rótulo de proveniência visível.
    readonly_fields = ("pricing_basis",)
    inlines = [QuotationPartInline]


@admin.register(QuotationPart)
class QuotationPartAdmin(admin.ModelAdmin):
    list_display = ("quotation", "template", "tema_letter", "material_sigla", "incluso", "sort_order")
    list_filter = ("incluso",)
