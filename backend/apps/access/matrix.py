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
- approval.*_sign: RBAC V2 M0; assinatura de estágios (ainda não enforced). technical={E},
  commercial={G,A}, quality/custom={A}. technical_sign vira dupla-condição com requires_crea em M1.
- role.manage: RBAC V2 M0; default admin-only (separa gerir papéis de editar a matriz).
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
    # RBAC V2 (M0) — assinatura de estágios. Defaults conservadores (ainda não enforced):
    # técnica só engenheiro (espelha o aprovador CREA atual; A fora — o trait requires_crea
    # de M1 é quem habilita); comercial no gestor + admin; qualidade/custom só admin até
    # existir uma role dedicada (criada pelo tenant em M2).
    "approval.technical_sign": frozenset({E}),
    "approval.commercial_sign": frozenset({G, A}),
    "approval.quality_sign": frozenset({A}),
    "approval.custom_sign_1": frozenset({A}),
    "approval.custom_sign_2": frozenset({A}),
    "approval.custom_sign_3": frozenset({A}),
    "cost_discovery.write": frozenset({E, A}),
    "rate.change": frozenset({E, G, A}),
    "rate.edit": frozenset({E, A}),
    # V2/F2 — aprovar propostas de knobs sensíveis (SoD; propor é rate.edit). Mesma turma
    # de rate.change {E,G,A} → qualquer par forma SoD válido; sole-qualified usa escape auditado.
    "knob.approve": frozenset({E, G, A}),
    "proposal.write": frozenset({E, A}),
    "tema_template.write": frozenset({E, A}),
    "material.read": frozenset({O, E, G, A}),
    "material.write": frozenset({E, G, A}),
    "nomus.reexport": frozenset({E, G, A}),
    "members.manage": frozenset({A}),
    "access.manage": frozenset({A}),
    "role.manage": frozenset({A}),
}

# Guarda-corpo: DEFAULT_MATRIX deve cobrir 1:1 o catálogo (drift = erro de deploy).
assert set(DEFAULT_MATRIX.keys()) == set(CAPABILITIES.keys()), (
    "DEFAULT_MATRIX fora de sincronia com CAPABILITIES: "
    f"faltando={set(CAPABILITIES) - set(DEFAULT_MATRIX)} "
    f"extra={set(DEFAULT_MATRIX) - set(CAPABILITIES)}"
)


# ── Estágios de aprovação default (T7) ───────────────────────────────────────
# APENAS o estágio built-in `technical` (aprovação técnica CREA), semeado required
# e travado. NÃO semeamos estágios adicionais (comercial etc.): a semântica deles
# depende do Wellington (Q10). Com só este estágio, `production.is_convertible` se
# comporta EXATAMENTE como antes do F10.
DEFAULT_STAGES = [
    {
        "key": "technical",
        "label": "Aprovação técnica (CREA)",
        "order": 10,
        "required": True,
        "approver_capability": "approval.request_remote",
        "is_builtin": True,
    },
]


def seed_approval_stages(*, model=None):
    """
    Semeia (idempotente) os estágios de aprovação default no schema ATIVO.

    Cria só o estágio built-in `technical` (required, travado). Usa update_or_create
    nos campos de sistema (label/order/approver_capability/is_builtin) para manter o
    built-in coerente, mas NÃO força `required` de volta em reexecuções — um admin
    NÃO pode desligar o técnico pela UI (é built-in), então `required` do técnico é
    de fato imutável; para estágios não-builtin (se existirem no futuro) preservamos
    a customização de `required` feita pelo admin.

    `model`: injeta o model histórico numa data migration (apps.get_model).
    Retorna {"created": int, "existing": int}.
    """
    if model is None:
        from apps.access.models import ApprovalStage as model  # noqa: N806

    created = existing = 0
    for spec in DEFAULT_STAGES:
        defaults = {
            "label": spec["label"],
            "order": spec["order"],
            "approver_capability": spec["approver_capability"],
            "is_builtin": spec["is_builtin"],
        }
        # `required` só entra no create (não sobrescreve customização de admin em
        # estágios não-builtin). O técnico é built-in => required travado em True.
        if spec["is_builtin"]:
            defaults["required"] = spec["required"]
            _obj, was_created = model.objects.update_or_create(
                key=spec["key"], defaults=defaults
            )
        else:
            defaults["required"] = spec["required"]
            _obj, was_created = model.objects.get_or_create(
                key=spec["key"], defaults=defaults
            )
        if was_created:
            created += 1
        else:
            existing += 1

    return {"created": created, "existing": existing}


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
