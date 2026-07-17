"""
UI de configuração do RBAC (T6): grade papel×capability.

- `access_config` (GET): renderiza a grade — linhas = capabilities agrupadas por
  `category` (registry `CAPABILITIES`), colunas = os 5 papéis (`ALL_ROLES`).
- `toggle_permission` (POST/HTMX): inverte `allowed` de um par (papel, capability),
  invalida o cache da matriz, audita e re-renderiza a parcial da LINHA.

Gating: `@require_capability("access.manage")` (fail-closed). Guard-rail anti-lockout:
recusa desligar a ÚLTIMA `access.manage=True` (senão o tenant se tranca fora).
"""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.access.capabilities import (
    CAPABILITIES,
    CAT_ADMIN,
    CAT_APPROVAL,
    CAT_CATALOG,
    CAT_ENGINEERING,
    CAT_INTEGRATION,
    CAT_PRODUCTION,
    CAT_PROPOSAL,
    CAT_QUOTATION,
    is_known_capability,
)
from apps.access.enforcement import invalidate_matrix_cache, require_capability
from apps.access.matrix import ALL_ROLES
from apps.access.models import ApprovalStage, RolePermission
from apps.accounts.models import UserProfile
from apps.audit.services import log_access

# Rótulos/ordem das categorias para a grade (apresentação; enforcement não usa isto).
CATEGORY_LABELS = {
    CAT_QUOTATION: "Cotações",
    CAT_PRODUCTION: "Produção / Ordens de Fabricação",
    CAT_APPROVAL: "Aprovações",
    CAT_ENGINEERING: "Engenharia (custeio / rates)",
    CAT_PROPOSAL: "Propostas",
    CAT_CATALOG: "Catálogos (TEMA / materiais)",
    CAT_INTEGRATION: "Integrações",
    CAT_ADMIN: "Administração do tenant",
}
CATEGORY_ORDER = [
    CAT_QUOTATION,
    CAT_PRODUCTION,
    CAT_APPROVAL,
    CAT_ENGINEERING,
    CAT_PROPOSAL,
    CAT_CATALOG,
    CAT_INTEGRATION,
    CAT_ADMIN,
]

_ROW_PARTIAL = "access/_config_row.html"
_STAGE_ROW_PARTIAL = "access/_stage_row.html"


def _role_header():
    """Cabeçalho de colunas: papéis na ordem canônica com rótulo humano."""
    labels = dict(UserProfile.ROLE)
    return [{"role": role, "label": labels.get(role, role)} for role in ALL_ROLES]


def _capability_row(code, perms=None, *, error=None):
    """
    Monta o dict de UMA linha da grade (capability × papéis).

    `perms`: mapa {(role, capability): allowed} já carregado (evita N queries);
    quando None, carrega só as linhas desta capability.
    """
    if perms is None:
        perms = {
            (rp.role, rp.capability): rp.allowed
            for rp in RolePermission.objects.filter(capability=code)
        }
    meta = CAPABILITIES[code]
    cells = [
        {"role": role, "allowed": bool(perms.get((role, code), False))}
        for role in ALL_ROLES
    ]
    return {
        "code": code,
        "row_id": code.replace(".", "-"),  # id de DOM seguro (sem ponto)
        "label": meta["label"],
        "description": meta["description"],
        "is_dangerous": meta["is_dangerous"],
        "cells": cells,
        "error": error,
    }


def _config_context():
    """Contexto completo da grade: grupos por categoria + cabeçalho de papéis."""
    perms = {
        (rp.role, rp.capability): rp.allowed for rp in RolePermission.objects.all()
    }
    by_category = {}
    for code, meta in CAPABILITIES.items():
        by_category.setdefault(meta["category"], []).append(code)

    groups = []
    for category in CATEGORY_ORDER:
        codes = by_category.get(category, [])
        if not codes:
            continue
        groups.append(
            {
                "category": category,
                "label": CATEGORY_LABELS.get(category, category),
                "rows": [_capability_row(code, perms) for code in codes],
            }
        )
    return {
        "groups": groups,
        "roles": _role_header(),
        "stages": _stage_rows(),
    }


def _stage_row(stage, *, error=None):
    """Dict de UMA linha da tabela de estágios de aprovação."""
    return {
        "pk": stage.pk,
        "key": stage.key,
        "row_id": stage.key.replace(".", "-"),
        "label": stage.label,
        "order": stage.order,
        "required": stage.required,
        "is_builtin": stage.is_builtin,
        "approver_capability": stage.approver_capability,
        "error": error,
    }


def _stage_rows():
    """Todos os estágios de aprovação do tenant, na ordem canônica (order, key)."""
    return [_stage_row(s) for s in ApprovalStage.objects.all().order_by("order", "key")]


@login_required
@require_capability("access.manage")
def access_config(request):
    """Página da grade papel×capability (config de níveis de acesso)."""
    return render(request, "access/config.html", _config_context())


def _last_access_manage(exclude_pk):
    """
    True se NÃO resta nenhuma outra linha access.manage=True além de `exclude_pk`.
    Base do guard-rail anti-lockout (nunca deixar o tenant sem quem gerencie acessos).
    """
    return not (
        RolePermission.objects.filter(capability="access.manage", allowed=True)
        .exclude(pk=exclude_pk)
        .exists()
    )


@require_POST
@require_capability("access.manage")
def toggle_permission(request):
    """
    Inverte `allowed` de um par (papel, capability) e re-renderiza a linha (HTMX).

    Fail-closed: papel fora de ALL_ROLES ou capability fora do catálogo -> 400.
    Anti-lockout: recusa desligar a última access.manage=True (mantém a linha ON).
    """
    role = (request.POST.get("role") or "").strip()
    capability = (request.POST.get("capability") or "").strip()

    if role not in ALL_ROLES or not is_known_capability(capability):
        return HttpResponseBadRequest("Papel ou capability inválido.")

    rp, _created = RolePermission.objects.get_or_create(
        role=role, capability=capability, defaults={"allowed": False}
    )
    new_allowed = not rp.allowed

    # Guard-rail anti-lockout: não remover o ÚLTIMO access.manage=True do tenant.
    if capability == "access.manage" and not new_allowed and _last_access_manage(rp.pk):
        row = _capability_row(
            capability,
            error="Não é possível remover a última permissão de gerenciar acessos "
            "(evita travar o tenant fora da administração).",
        )
        return render(request, _ROW_PARTIAL, {"cap": row}, status=400)

    rp.allowed = new_allowed
    rp.updated_by = request.user  # FK aponta para AUTH_USER_MODEL (User), não profile
    rp.save(update_fields=["allowed", "updated_by", "updated_at"])

    invalidate_matrix_cache()  # o signal já invalida; explícito por robustez (T3)
    log_access(
        request,
        "permission_change",
        rp,
        {"role": role, "capability": capability, "allowed": new_allowed},
    )

    return render(request, _ROW_PARTIAL, {"cap": _capability_row(capability)})


@require_POST
@require_capability("access.manage")
def toggle_stage(request):
    """
    Inverte `required` de um ApprovalStage e re-renderiza a linha (HTMX).

    Compliance: estágios `is_builtin=True` (aprovação técnica CREA) têm `required`
    TRAVADO — o toggle é recusado (400) e a linha volta com o estado original. Isto
    garante que `is_convertible` sempre exija a aprovação técnica CREA.
    """
    key = (request.POST.get("key") or "").strip()
    stage = ApprovalStage.objects.filter(key=key).first()
    if stage is None:
        return HttpResponseBadRequest("Estágio de aprovação inválido.")

    if stage.is_builtin:
        # Built-in (CREA): required é imutável por compliance. Recusa o toggle.
        row = _stage_row(
            stage,
            error="A aprovação técnica (CREA) é obrigatória por compliance e não "
            "pode ser desativada.",
        )
        return render(request, _STAGE_ROW_PARTIAL, {"stage": row}, status=400)

    stage.required = not stage.required
    stage.updated_by = request.user
    stage.save(update_fields=["required", "updated_by", "updated_at"])

    log_access(
        request,
        "approval_config_change",
        stage,
        {"key": stage.key, "required": stage.required},
    )

    return render(request, _STAGE_ROW_PARTIAL, {"stage": _stage_row(stage)})
