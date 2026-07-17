"""
DEFAULT_MATRIX — matriz papel×capability default, derivada LITERAL das tuplas de
papéis hoje hardcoded nas views (fonte da verdade a migrar). Cada capability lista
o conjunto de papéis com `allowed=True`; qualquer papel fora do conjunto = negado.

Referências (F10_RBAC_CONFIG_PLAN.md + grep das views):
- quotation.create      -> quotations/views.py _ENTRY_ROLES  = {O, E, A}
- quotation.write       -> quotations/views.py _WRITE_ROLES  = {O, E, G, A}
- quotation.read        -> quotations/views.py _READ_ROLES   = {V, O, E, G, A}
- quotation.price_api   -> quotations/api.py   _WRITE_ROLES  = {O, E, G, A}
- of.convert            -> production/views.py  _OF_CONVERT_ROLES = {E, G, A}  (orcamentista FORA)
- of.transition         -> production/views.py  _OF_TRANSITION_ROLES = _ITP_ROLES = {E, A}
- itp.manage            -> production/views.py  _ITP_ROLES   = {E, A}
- approval.request_remote     -> audit/views.py _WRITE_ROLES = {O, E, G, A}
- approval.request_presencial -> audit/views.py _WRITE_ROLES = {O, E, G, A}
- approval.panel_read         -> audit/views.py _READ_ROLES  = {O, E, G, A}
- cost_discovery.write  -> cost_discovery/views.py _WRITE_ROLES = {E, A}
- rate.change           -> engineering_params/views.py _ROLES_ALTERAM_RATE = {E, G, A}
- rate.edit             -> engineering_params/views.py _ROLES_EDITAM_RATE  = {E, A}
- proposal.write        -> proposals/views.py _WRITE_ROLES  = {E, A}
- tema_template.write   -> tema_templates/views.py _WRITE_ROLES = {E, A}
- material.read         -> materials/views.py _READ_ROLES   = {O, E, G, A}  (todos exceto viewer)
- material.write        -> materials/views.py _WRITE_ROLES  = {E, G, A}
- nomus.reexport        -> integrations/nomus/views.py _REEXPORT_ROLES = {E, G, A}
- members.manage        -> accounts/views.py @require_role(ADMIN) = {A}
- access.manage         -> NOVO; default admin-only (Wellington Q9; gestor_comercial fica False até validar)
"""
from apps.accounts.models import UserProfile
from apps.access.capabilities import CAPABILITIES

V = UserProfile.ROLE_VIEWER
O = UserProfile.ROLE_ORCAMENTISTA
E = UserProfile.ROLE_ENGENHEIRO
G = UserProfile.ROLE_GESTOR_COMERCIAL
A = UserProfile.ROLE_ADMIN

# Ordem canônica dos papéis (para a grade e para gerar linhas de todas as células).
ALL_ROLES = [V, O, E, G, A]

DEFAULT_MATRIX = {
    "quotation.create": frozenset({O, E, A}),
    "quotation.write": frozenset({O, E, G, A}),
    "quotation.read": frozenset({V, O, E, G, A}),
    "quotation.price_api": frozenset({O, E, G, A}),
    "of.convert": frozenset({E, G, A}),
    "of.transition": frozenset({E, A}),
    "itp.manage": frozenset({E, A}),
    "approval.request_remote": frozenset({O, E, G, A}),
    "approval.request_presencial": frozenset({O, E, G, A}),
    "approval.panel_read": frozenset({O, E, G, A}),
    "cost_discovery.write": frozenset({E, A}),
    "rate.change": frozenset({E, G, A}),
    "rate.edit": frozenset({E, A}),
    "proposal.write": frozenset({E, A}),
    "tema_template.write": frozenset({E, A}),
    "material.read": frozenset({O, E, G, A}),
    "material.write": frozenset({E, G, A}),
    "nomus.reexport": frozenset({E, G, A}),
    "members.manage": frozenset({A}),
    "access.manage": frozenset({A}),
}

# Guarda-corpo: DEFAULT_MATRIX deve cobrir 1:1 o catálogo (drift = erro de deploy).
assert set(DEFAULT_MATRIX.keys()) == set(CAPABILITIES.keys()), (
    "DEFAULT_MATRIX fora de sincronia com CAPABILITIES: "
    f"faltando={set(CAPABILITIES) - set(DEFAULT_MATRIX)} "
    f"extra={set(DEFAULT_MATRIX) - set(CAPABILITIES)}"
)


def seed_access_matrix(*, model=None, updated_by=None):
    """
    Semeia (idempotente) a matriz papel×capability no schema ATIVO.

    Cria uma linha RolePermission para CADA par (papel, capability) com
    `allowed = papel in DEFAULT_MATRIX[capability]`. Usa get_or_create: NÃO
    sobrescreve customizações já feitas por um admin (só preenche lacunas).
    Reexecutar é no-op (backfill retroativo seguro).

    `model`: injeta o model histórico numa data migration (apps.get_model).
    Retorna {"created": int, "existing": int}.
    """
    if model is None:
        from apps.access.models import RolePermission as model  # noqa: N806

    created = existing = 0
    for capability in CAPABILITIES:
        allowed_roles = DEFAULT_MATRIX.get(capability, frozenset())
        for role in ALL_ROLES:
            defaults = {"allowed": role in allowed_roles}
            if updated_by is not None:
                defaults["updated_by"] = updated_by
            _obj, was_created = model.objects.get_or_create(
                role=role, capability=capability, defaults=defaults
            )
            if was_created:
                created += 1
            else:
                existing += 1

    # Invalida o cache da matriz do schema (import tardio: evita ciclo/registry).
    try:
        from apps.access.enforcement import invalidate_matrix_cache

        invalidate_matrix_cache()
    except Exception:  # pragma: no cover - cache é best-effort
        pass

    return {"created": created, "existing": existing}
