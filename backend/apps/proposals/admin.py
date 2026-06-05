from django.contrib import admin
from apps.proposals.models import ProposalTemplate, Proposal


@admin.register(ProposalTemplate)
class ProposalTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default", "is_active", "company_name", "delivery_weeks", "validity_days")
    list_filter = ("is_default", "is_active")


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ("number", "quotation", "status", "generated_at")
    list_filter = ("status",)
    readonly_fields = ("docx_sha256", "pdf_sha256", "generated_at")
