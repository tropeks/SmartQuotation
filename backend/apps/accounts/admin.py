"""Admin do app accounts."""
from django.contrib import admin

from apps.accounts.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "role", "crea_number", "crea_state", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("full_name", "user__username", "user__email", "crea_number")
    autocomplete_fields = ("user",)
