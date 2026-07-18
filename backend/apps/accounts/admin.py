"""Admin do app accounts."""
from django.contrib import admin

from apps.accounts.models import Role, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "role", "crea_number", "crea_state", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("full_name", "user__username", "user__email", "crea_number")
    autocomplete_fields = ("user",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "requires_crea", "is_admin_like", "is_seeded")
    list_filter = ("requires_crea", "is_admin_like", "is_seeded")
    search_fields = ("key", "name", "description")
    readonly_fields = ("updated_at",)
