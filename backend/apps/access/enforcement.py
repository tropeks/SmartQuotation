"""
Enforcement do RBAC configurável (fail-closed).

- `role_can(role, cap)`   -> bool: o papel PODE a capability? (fonte: RolePermission)
- `user_can(user, cap)`   -> bool: idem, resolvendo o papel do usuário (flags de template).
- `require_capability(cap, allow_platform_staff=False)`: decorator de view com a MESMA
  semântica de `accounts.rbac.require_role` (não autenticado -> login; sem permissão -> 403).

Fail-closed em todos os pontos:
- capability fora do catálogo (`capabilities.py`) -> False;
- papel sem linha `allowed=True` para a capability -> False;
- usuário sem papel (ex.: staff de plataforma sem UserProfile) -> False em `user_can`
  (mantém a semântica exata das flags de template atuais; o bypass de staff é
  responsabilidade explícita de `require_capability(..., allow_platform_staff=True)`).

Cache: a matriz papel×capability é lida do banco 1x por schema e cacheada com a chave
`access:matrix:{schema_name}` (tenant-aware). Invalidada no save/delete de RolePermission.
Sem CACHES configurado, o backend é LocMemCache por processo — suficiente single-node;
multi-node exige Redis (ver T8/docs).
"""
from functools import wraps

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.shortcuts import redirect

from apps.accounts.rbac import user_role
from apps.access.capabilities import is_known_capability

_CACHE_PREFIX = "access:matrix:"
_CACHE_TTL = 300  # segundos; invalidação explícita no save cobre a maior parte


def _cache_key(schema_name=None):
    schema = schema_name or connection.schema_name
    return f"{_CACHE_PREFIX}{schema}"


def _load_matrix():
    """
    Retorna {role: frozenset(capabilities permitidas)} para o schema ATIVO.
    Lê do cache; em miss, monta do banco (RolePermission allowed=True) e cacheia.
    """
    key = _cache_key()
    matrix = cache.get(key)
    if matrix is not None:
        return matrix

    # Import tardio: evita AppRegistryNotReady em import de módulo.
    from apps.access.models import RolePermission

    matrix = {}
    rows = RolePermission.objects.filter(allowed=True).values_list("role", "capability")
    for role, capability in rows:
        matrix.setdefault(role, set()).add(capability)
    matrix = {role: frozenset(caps) for role, caps in matrix.items()}

    cache.set(key, matrix, _CACHE_TTL)
    return matrix


def invalidate_matrix_cache(schema_name=None):
    """Descarta o cache da matriz do schema (chamado nos signals de RolePermission)."""
    cache.delete(_cache_key(schema_name))


def role_can(role, capability_code):
    """
    True se `role` tem `capability_code` permitida no schema ativo. Fail-closed:
    papel None/vazio, capability desconhecida ou sem linha allowed=True -> False.
    """
    if not role:
        return False
    if not is_known_capability(capability_code):
        return False
    matrix = _load_matrix()
    return capability_code in matrix.get(role, frozenset())


def user_can(user, capability_code):
    """
    True se o papel do `user` tem a capability. Usado para flags de template
    (mesma fonte do enforcement -> sem flicker). Staff sem UserProfile -> False.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return role_can(user_role(user), capability_code)


def require_capability(capability_code, allow_platform_staff=False):
    """
    Decorator de view. Mesma semântica de `accounts.rbac.require_role`:
    - não autenticado -> redireciona para login;
    - allow_platform_staff=True: is_staff/is_superuser passam mesmo sem UserProfile
      (usar só em views de LEITURA);
    - autenticado sem a capability -> PermissionDenied (HTTP 403).
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return redirect("login")
            if allow_platform_staff and (user.is_superuser or user.is_staff):
                return view_func(request, *args, **kwargs)
            if not user_can(user, capability_code):
                raise PermissionDenied("Papel sem permissão para este recurso.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
