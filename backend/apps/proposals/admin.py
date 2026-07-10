from django.contrib import admin
from apps.proposals.models import ProposalTemplate, Proposal, ProposalVersion


@admin.register(ProposalTemplate)
class ProposalTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default", "is_active", "company_name", "delivery_weeks", "validity_days")
    list_filter = ("is_default", "is_active")


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ("number", "quotation", "status", "generated_at")
    list_filter = ("status",)
    readonly_fields = ("docx_sha256", "pdf_sha256", "generated_at")


@admin.register(ProposalVersion)
class ProposalVersionAdmin(admin.ModelAdmin):
    list_display = ("proposal", "version_number", "generated_at", "generated_by", "emailed_at", "email_to")
    list_filter = ("generated_at", "emailed_at")
    readonly_fields = ("generated_at", "emailed_at")
