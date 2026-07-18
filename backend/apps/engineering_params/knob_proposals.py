"""Serviço das propostas de mudança de knobs sensíveis (Config de Engenharia V2 / F2, Bloco B lite).

Dupla validação com SEPARAÇÃO DE FUNÇÕES (SoD): um propõe (rate.edit), outro aprova (knob.approve).
Espelha o escape auditado do RBAC V2 (audit/approvals.py) — quem propõe não aprova a própria,
salvo se NÃO houver outro usuário ativo qualificado (self_approved auditado). NÃO usa o ApprovalCase
(acoplado a Quotation). Aplica ao TenantParamConfig on-approve, atomicamente, com trilha de auditoria.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.engineering_params.models import KnobChangeProposal, TenantParamConfig

KNOB_APPROVE_CAP = "knob.approve"
# campos do TenantParamConfig que são knobs SENSÍVEIS (entram no cálculo) → sob aprovação.
SENSITIVE_KNOB_FIELDS = ("perda_por_familia", "setup_frac")


def _coerce(raw):
    from apps.quotations.adapter import _coerce_factor_map
    return _coerce_factor_map(raw, "knob")


def _num(v):
    try:
        return round(float(v), 9)
    except (TypeError, ValueError):
        return None


def _other_qualified_exists(exclude_user):
    """True se existe OUTRO usuário ativo qualificado p/ aprovar (base do escape de SoD)."""
    from apps.accounts.models import UserProfile
    from apps.access.enforcement import role_can
    for prof in UserProfile.objects.filter(is_active=True).exclude(user=exclude_user):
        if role_can(prof.role, KNOB_APPROVE_CAP):
            return True
    return False


def create_proposal(user, after):
    """Cria proposta PENDING com o diff (before=vigente, after=proposto). `after` = {campo: {k: v}},
    só campos em SENSITIVE_KNOB_FIELDS. Recusa se já há uma pendente (1 lote por vez)."""
    cfg = TenantParamConfig.get_solo()
    payload = {}
    for field in SENSITIVE_KNOB_FIELDS:
        proposto = _coerce((after or {}).get(field, {}))
        if not proposto:
            continue
        vigente = getattr(cfg, field) or {}
        before = {k: vigente.get(k) for k in proposto}
        payload[field] = {"before": before, "after": proposto}
    if not payload:
        raise ValidationError("Nenhum knob sensível na proposta.")
    with transaction.atomic():
        if KnobChangeProposal.objects.filter(status=KnobChangeProposal.STATUS_PENDING).exists():
            raise ValidationError("Já existe uma proposta de knobs pendente.")
        return KnobChangeProposal.objects.create(
            payload=payload, requested_by=user, status=KnobChangeProposal.STATUS_PENDING)


def approve_proposal(pk, approver, request=None):
    """Aprova e APLICA a proposta ao TenantParamConfig. Enforce: capability, SoD e staleness.
    Levanta PermissionDenied (capability/SoD) ou ValidationError (staleness)."""
    from apps.access.enforcement import user_can
    with transaction.atomic():
        p = KnobChangeProposal.objects.select_for_update().get(
            pk=pk, status=KnobChangeProposal.STATUS_PENDING)

        if not user_can(approver, KNOB_APPROVE_CAP):
            raise PermissionDenied("Sem permissão para aprovar knobs.")

        # SoD: quem propôs não aprova a própria — salvo se é o único qualificado (escape auditado).
        self_approved = False
        if p.requested_by_id and p.requested_by_id == approver.pk:
            if _other_qualified_exists(exclude_user=approver):
                raise PermissionDenied(
                    "Separação de funções: quem propôs não aprova a própria proposta.")
            self_approved = True

        cfg = TenantParamConfig.objects.select_for_update().get(pk=1)

        # staleness: a config vigente mudou (nas chaves propostas) desde a proposta?
        for field, diff in p.payload.items():
            atual = getattr(cfg, field, {}) or {}
            before = diff.get("before", {})
            for k in diff.get("after", {}):
                if _num(atual.get(k)) != _num(before.get(k)):
                    raise ValidationError(
                        "A configuração vigente mudou desde a proposta; refaça a proposta.")

        # aplica (só as chaves da proposta; preserva o resto)
        for field, diff in p.payload.items():
            atual = dict(getattr(cfg, field, {}) or {})
            atual.update(_coerce(diff.get("after", {})))
            setattr(cfg, field, atual)
        cfg.save(update_fields=list(p.payload.keys()))

        p.status = KnobChangeProposal.STATUS_APPLIED
        p.resolved_by = approver
        p.resolved_at = timezone.now()
        p.self_approved = self_approved
        p.save(update_fields=["status", "resolved_by", "resolved_at", "self_approved"])

        if request is not None:
            from apps.audit.services import log_access
            log_access(request, "param_change", cfg, {
                "knob": "config_engenharia_v2",
                "proposal_id": p.pk,
                "self_approved": self_approved,
                "anterior": {f: d.get("before") for f, d in p.payload.items()},
                "novo": {f: d.get("after") for f, d in p.payload.items()},
            })
    return p


def reject_proposal(pk, user):
    """Rejeita a proposta pendente (sem mutar o TenantParamConfig)."""
    with transaction.atomic():
        p = KnobChangeProposal.objects.select_for_update().get(
            pk=pk, status=KnobChangeProposal.STATUS_PENDING)
        p.status = KnobChangeProposal.STATUS_REJECTED
        p.resolved_by = user
        p.resolved_at = timezone.now()
        p.save(update_fields=["status", "resolved_by", "resolved_at"])
    return p
