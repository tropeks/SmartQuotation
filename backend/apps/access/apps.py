from django.apps import AppConfig


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access"
    label = "access"
    verbose_name = "Controle de Acesso (RBAC configurável)"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.access.models import RolePermission
        from apps.access.signals import invalidate_matrix_on_change

        post_save.connect(
            invalidate_matrix_on_change,
            sender=RolePermission,
            dispatch_uid="access_rolepermission_post_save",
        )
        post_delete.connect(
            invalidate_matrix_on_change,
            sender=RolePermission,
            dispatch_uid="access_rolepermission_post_delete",
        )
