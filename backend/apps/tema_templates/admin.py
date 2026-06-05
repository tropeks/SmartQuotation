from django.contrib import admin
from apps.tema_templates.models import ComponentTemplate


@admin.register(ComponentTemplate)
class ComponentTemplateAdmin(admin.ModelAdmin):
    list_display = ("tema_part", "tema_letter", "name", "is_global", "is_active")
    list_filter = ("tema_part", "is_global", "is_active")
    search_fields = ("name", "tema_letter", "standard_ref")
