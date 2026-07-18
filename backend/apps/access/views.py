"""
UI de configuração do RBAC (T6): grade papel×capability.

- `access_config` (GET): renderiza a grade — linhas = capabilities agrupadas por
  `category` (registry `CAPABILITIES`), colunas = papéis do tenant (`Role.ordered()`).
- `toggle_permission` (POST/HTMX): inverte `allowed` de um par (papel, capability),
  invalida o cache da matriz, audita e re-renderiza a parcial da LINHA.

Gating: `@require_capability("access.manage")` (fail-closed). Guard-rail anti-lockout:
recusa desligar a ÚLTIMA `access.manage=True` (senão o tenant se tranca fora).
"""
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.text import slugify
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
from apps.access.compliance import TECHNICAL_SIGN_CAP
from apps.access.enforcement import invalidate_matrix_cache, require_capability
from apps.access.models import ApprovalStage, RolePermission
from apps.access.role_templates import TEMPLATE_VERSION, get_template, role_templates
from apps.accounts.models import Role, UserProfile
from apps.audit.services import log_access

# Guard-rail: teto de papéis por tenant (decisão do Rom; config por plano é V2.1).
MAX_ROLES_PER_TENANT = 15

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


def _role_keys(role_keys=None):
    """Keys dos papéis do tenant na ordem canônica (built-ins + custom). M2: dinâmico."""
    if role_keys is not None:
        return role_keys
    return [r.key for r in Role.ordered()]


def _role_header():
    """Cabeçalho de colunas: papéis do tenant (Role) na ordem canônica, com nome humano."""
    return [{"role": r.key, "label": r.name} for r in Role.ordered()]


def _capability_row(code, perms=None, *, role_keys=None, error=None):
    """
    Monta o dict de UMA linha da grade (capability × papéis).

    `perms`: mapa {(role, capability): allowed} já carregado (evita N queries);
    quando None, carrega só as linhas desta capability.
    `role_keys`: colunas (papéis) já ordenadas; quando None, consulta Role.ordered().
    """
    if perms is None:
        perms = {
            (rp.role, rp.capability): rp.allowed
            for rp in RolePermission.objects.filter(capability=code)
        }
    role_keys = _role_keys(role_keys)
    meta = CAPABILITIES[code]
    cells = [
        {"role": role, "allowed": bool(perms.get((role, code), False))}
        for role in role_keys
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
    role_keys = _role_keys()
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
                "rows": [_capability_row(code, perms, role_keys=role_keys) for code in codes],
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


# Capabilities de administração que NÃO podem ficar sem nenhum papel (anti-lockout G8).
_LOCKOUT_CAPS = ("access.manage", "role.manage")


def _is_last_grant(capability, exclude_pk):
    """
    True se NÃO resta nenhuma outra linha `capability`=True além de `exclude_pk`.
    Base do guard-rail anti-lockout: nunca deixar o tenant sem quem gerencie
    acessos (`access.manage`) ou papéis (`role.manage`).
    """
    return not (
        RolePermission.objects.filter(capability=capability, allowed=True)
        .exclude(pk=exclude_pk)
        .exists()
    )


@require_POST
@require_capability("access.manage")
def toggle_permission(request):
    """
    Inverte `allowed` de um par (papel, capability) e re-renderiza a linha (HTMX).

    Fail-closed: papel inexistente na tabela Role ou capability fora do catálogo -> 400.
    Anti-lockout: recusa desligar a última access.manage=True (mantém a linha ON).
    """
    role = (request.POST.get("role") or "").strip()
    capability = (request.POST.get("capability") or "").strip()

    if not Role.objects.filter(key=role).exists() or not is_known_capability(capability):
        return HttpResponseBadRequest("Papel ou capability inválido.")

    # Invariante de compliance (#86): não conceder assinatura técnica a papel sem CREA.
    if (
        capability == TECHNICAL_SIGN_CAP
        and not Role.objects.filter(key=role, requires_crea=True).exists()
    ):
        rp_existing = RolePermission.objects.filter(role=role, capability=capability).first()
        will_enable = not (rp_existing.allowed if rp_existing else False)
        if will_enable:
            row = _capability_row(
                capability,
                error="Só papéis com CREA (trait requires_crea) podem assinar a "
                "aprovação técnica. Ative 'Exige CREA' no papel primeiro.",
            )
            return render(request, _ROW_PARTIAL, {"cap": row}, status=400)

    rp, _created = RolePermission.objects.get_or_create(
        role=role, capability=capability, defaults={"allowed": False}
    )
    new_allowed = not rp.allowed

    # Guard-rail anti-lockout: não remover o ÚLTIMO access.manage/role.manage do tenant.
    if capability in _LOCKOUT_CAPS and not new_allowed and _is_last_grant(capability, rp.pk):
        alvo = "gerenciar acessos" if capability == "access.manage" else "gerenciar papéis"
        row = _capability_row(
            capability,
            error=f"Não é possível remover a última permissão de {alvo} "
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


# ─────────────────────────────────────────────────────────────────────────────
# RBAC V2 M2 — Página "Papéis" (papéis como dado). Gate `role.manage`.
# ─────────────────────────────────────────────────────────────────────────────

def _role_summary(role):
    """Linha da lista de papéis: origem, traits e nº de usuários ativos."""
    active_users = UserProfile.objects.filter(role=role.key, is_active=True).count()
    if role.is_seeded:
        origin = "Padrão"
    elif role.source_template:
        origin = f"Template · v{role.template_version or TEMPLATE_VERSION}"
    else:
        origin = "Do zero"
    return {
        "key": role.key,
        "name": role.name,
        "description": role.description,
        "requires_crea": role.requires_crea,
        "is_admin_like": role.is_admin_like,
        "is_seeded": role.is_seeded,
        "active_users": active_users,
        "origin": origin,
    }


def _role_cap_grid(selected_codes):
    """Grade de capabilities agrupada por categoria, com estado `checked` por `selected_codes`."""
    by_category = {}
    for code, meta in CAPABILITIES.items():
        by_category.setdefault(meta["category"], []).append(code)
    groups = []
    for category in CATEGORY_ORDER:
        codes = by_category.get(category, [])
        if not codes:
            continue
        groups.append({
            "category": category,
            "label": CATEGORY_LABELS.get(category, category),
            "caps": [{
                "code": code,
                "label": CAPABILITIES[code]["label"],
                "description": CAPABILITIES[code]["description"],
                "is_dangerous": CAPABILITIES[code]["is_dangerous"],
                "checked": code in selected_codes,
            } for code in codes],
        })
    return groups


def _selected_caps(request):
    """Capabilities marcadas no POST do formulário (checkbox name='cap'), filtradas pelo catálogo."""
    return {c for c in request.POST.getlist("cap") if is_known_capability(c)}


def _unique_role_key(name):
    """Gera uma key slug única a partir do nome (viewer, tecnico-senior, ...)."""
    base = slugify(name)[:32] or "papel"
    key = base
    i = 2
    while Role.objects.filter(key=key).exists():
        suffix = f"-{i}"
        key = f"{base[:32 - len(suffix)]}{suffix}"
        i += 1
    return key


@login_required
@require_capability("role.manage")
def roles_list(request):
    """Lista de papéis do tenant + entrada para criação (gate role.manage)."""
    roles = [_role_summary(r) for r in Role.ordered()]
    total = len(roles)
    return render(request, "access/roles_list.html", {
        "roles": roles,
        "templates": role_templates(),
        "max_roles": MAX_ROLES_PER_TENANT,
        "at_limit": total >= MAX_ROLES_PER_TENANT,
        "total": total,
        "notice": request.GET.get("notice", ""),
    })


@login_required
@require_capability("role.manage")
def role_new(request):
    """Formulário de criação. `?template=<key>` pré-preenche nome/traits/grade; 'blank' = do zero."""
    tpl = get_template(request.GET.get("template", ""))
    if Role.objects.count() >= MAX_ROLES_PER_TENANT:
        return redirect(f"{_roles_url()}?notice=limit")
    selected = set(tpl["capabilities"]) if tpl else set()
    ctx = {
        "mode": "create",
        "form_action": "access:role_create",
        "role": {
            "key": "",
            "name": tpl["name"] if tpl else "",
            "description": tpl["description"] if tpl else "",
            "requires_crea": tpl["requires_crea"] if tpl else False,
            "is_admin_like": tpl["is_admin_like"] if tpl else False,
        },
        "source_template": tpl["key"] if tpl else "",
        "cap_groups": _role_cap_grid(selected),
        "is_seeded": False,
        "editable_key": True,
    }
    return render(request, "access/role_form.html", ctx)


def _roles_url():
    from django.urls import reverse
    return reverse("access:roles")


def _render_role_form_error(request, *, mode, role_ctx, source_template, selected, error, is_seeded, key=""):
    ctx = {
        "mode": mode,
        "form_action": "access:role_create" if mode == "create" else "access:role_update",
        "role": role_ctx,
        "source_template": source_template,
        "cap_groups": _role_cap_grid(selected),
        "is_seeded": is_seeded,
        "editable_key": mode == "create",
        "error": error,
        "edit_key": key,
    }
    return render(request, "access/role_form.html", ctx, status=400)


@require_POST
@require_capability("role.manage")
def role_create(request):
    """Cria um papel custom + suas linhas RolePermission. Guard-rails: teto, compliance."""
    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    requires_crea = bool(request.POST.get("requires_crea"))
    is_admin_like = bool(request.POST.get("is_admin_like"))
    source_template = (request.POST.get("source_template") or "").strip()
    selected = _selected_caps(request)

    role_ctx = {
        "key": "", "name": name, "description": description,
        "requires_crea": requires_crea, "is_admin_like": is_admin_like,
    }

    def err(msg):
        return _render_role_form_error(
            request, mode="create", role_ctx=role_ctx, source_template=source_template,
            selected=selected, error=msg, is_seeded=False,
        )

    if Role.objects.count() >= MAX_ROLES_PER_TENANT:
        return err(f"Limite de {MAX_ROLES_PER_TENANT} papéis por tenant atingido.")
    if not name:
        return err("Informe o nome do papel.")
    # Invariante de compliance (#86): assinatura técnica exige o trait requires_crea.
    if TECHNICAL_SIGN_CAP in selected and not requires_crea:
        return err("Papéis que assinam a aprovação técnica precisam do trait 'Exige CREA'.")

    key = _unique_role_key(name)
    with transaction.atomic():
        role = Role.objects.create(
            key=key, name=name, description=description,
            requires_crea=requires_crea, is_admin_like=is_admin_like,
            is_seeded=False,
            source_template=source_template,
            template_version=TEMPLATE_VERSION if source_template else None,
            updated_by=request.user,
        )
        RolePermission.objects.bulk_create([
            RolePermission(role=key, capability=code, allowed=(code in selected),
                           updated_by=request.user)
            for code in CAPABILITIES
        ])
    invalidate_matrix_cache()
    log_access(request, "role_change", role, {
        "action": "create", "key": key, "name": name,
        "requires_crea": requires_crea, "is_admin_like": is_admin_like,
        "capabilities": sorted(selected), "source_template": source_template,
    })
    return redirect(f"{_roles_url()}?notice=created")


@login_required
@require_capability("role.manage")
def role_edit(request, key):
    """Formulário de edição de um papel (nome/descrição/traits + grade de capabilities)."""
    role = Role.objects.filter(key=key).first()
    if role is None:
        return redirect(_roles_url())
    selected = {
        rp.capability for rp in RolePermission.objects.filter(role=key, allowed=True)
    }
    ctx = {
        "mode": "edit",
        "form_action": "access:role_update",
        "role": {
            "key": role.key, "name": role.name, "description": role.description,
            "requires_crea": role.requires_crea, "is_admin_like": role.is_admin_like,
        },
        "source_template": role.source_template,
        "cap_groups": _role_cap_grid(selected),
        "is_seeded": role.is_seeded,
        "editable_key": False,
        "edit_key": role.key,
        "active_users": UserProfile.objects.filter(role=key, is_active=True).count(),
        "reassign_targets": [r for r in Role.ordered() if r.key != key],
    }
    return render(request, "access/role_form.html", ctx)


@require_POST
@require_capability("role.manage")
def role_update(request):
    """Atualiza nome/descrição/traits + matriz do papel. Guard-rails: anti-lockout, compliance."""
    key = (request.POST.get("key") or "").strip()
    role = Role.objects.filter(key=key).first()
    if role is None:
        return redirect(_roles_url())

    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    requires_crea = bool(request.POST.get("requires_crea"))
    is_admin_like = bool(request.POST.get("is_admin_like"))
    selected = _selected_caps(request)

    role_ctx = {
        "key": key, "name": name, "description": description,
        "requires_crea": requires_crea, "is_admin_like": is_admin_like,
    }

    def err(msg):
        return _render_role_form_error(
            request, mode="edit", role_ctx=role_ctx, source_template=role.source_template,
            selected=selected, error=msg, is_seeded=role.is_seeded, key=key,
        )

    if not name:
        return err("Informe o nome do papel.")
    # Compliance (#86): technical_sign exige requires_crea (nas duas direções).
    if TECHNICAL_SIGN_CAP in selected and not requires_crea:
        return err("Papéis que assinam a aprovação técnica precisam do trait 'Exige CREA'.")
    # Anti-lockout (G8): não remover o último access.manage/role.manage do tenant.
    for cap in _LOCKOUT_CAPS:
        if cap not in selected and _role_is_last_grant_of(key, cap):
            alvo = "gerenciar acessos" if cap == "access.manage" else "gerenciar papéis"
            return err(f"Este é o único papel que pode {alvo}; não é possível remover essa permissão.")

    with transaction.atomic():
        role.name = name
        role.description = description
        role.requires_crea = requires_crea
        role.is_admin_like = is_admin_like
        role.updated_by = request.user
        role.save(update_fields=[
            "name", "description", "requires_crea", "is_admin_like",
            "updated_by", "updated_at",
        ])
        for code in CAPABILITIES:
            RolePermission.objects.update_or_create(
                role=key, capability=code,
                defaults={"allowed": (code in selected), "updated_by": request.user},
            )
    invalidate_matrix_cache()
    log_access(request, "role_change", role, {
        "action": "update", "key": key, "name": name,
        "requires_crea": requires_crea, "is_admin_like": is_admin_like,
        "capabilities": sorted(selected),
    })
    return redirect(f"{_roles_url()}?notice=updated")


def _role_is_last_grant_of(key, capability):
    """True se `key` é o ÚNICO papel com `capability`=True (base do anti-lockout no update/delete)."""
    holders = set(
        RolePermission.objects.filter(capability=capability, allowed=True)
        .values_list("role", flat=True)
    )
    return holders == {key}


@require_POST
@require_capability("role.manage")
def role_delete(request):
    """
    Exclui um papel CUSTOM. Papéis built-in (is_seeded) são estruturais e NÃO
    podem ser excluídos. Com usuários ativos, exige reatribuição em massa (reassign_to).
    Anti-lockout: não excluir o único papel com access.manage/role.manage.
    """
    key = (request.POST.get("key") or "").strip()
    role = Role.objects.filter(key=key).first()
    if role is None:
        return redirect(_roles_url())
    if role.is_seeded:
        return redirect(f"{_roles_url()}?notice=builtin")

    # Anti-lockout: não excluir o único papel que administra acessos/papéis.
    for cap in _LOCKOUT_CAPS:
        if _role_is_last_grant_of(key, cap):
            return redirect(f"{_roles_url()}?notice=lockout")

    active = UserProfile.objects.filter(role=key, is_active=True)
    active_count = active.count()
    reassign_to = (request.POST.get("reassign_to") or "").strip()
    if active_count:
        target = Role.objects.filter(key=reassign_to).first()
        if target is None or target.key == key:
            return redirect(f"{_roles_url()}?notice=need_reassign")
        # Compliance: só reatribuir para papel com CREA se todos os movidos tiverem CREA.
        if target.requires_crea and active.filter(crea_number="").exists():
            return redirect(f"{_roles_url()}?notice=reassign_crea")

    with transaction.atomic():
        moved = 0
        if active_count:
            moved = UserProfile.objects.filter(role=key).update(role=reassign_to)
        RolePermission.objects.filter(role=key).delete()
        role.delete()
    invalidate_matrix_cache()
    log_access(request, "role_change", None, {
        "action": "delete", "key": key, "reassigned_to": reassign_to or None,
        "users_moved": moved,
    })
    return redirect(f"{_roles_url()}?notice=deleted")
