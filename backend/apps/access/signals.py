"""Signals do app access: invalidam o cache da matriz no save/delete de RolePermission."""
from apps.access.enforcement import invalidate_matrix_cache


def invalidate_matrix_on_change(sender, instance, **kwargs):
    """
    Descarta o cache da matriz do schema ativo. O save/delete ocorre dentro do
    contexto de schema do tenant, então `connection.schema_name` (via
    invalidate_matrix_cache) resolve a chave correta.
    """
    invalidate_matrix_cache()
