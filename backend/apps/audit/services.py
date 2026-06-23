"""Serviços de auditoria H1."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AccessLog, TechnicalApproval


def latest_snapshot_for(quotation):
    return quotation.snapshots.order_by("-created_at", "-id").first()


@transaction.atomic
def approve_quotation(quotation, approved_by, art_number="", notes="", request=None):
    snapshot = latest_snapshot_for(quotation)
    if snapshot is None:
        raise ValidationError("Cotação sem CalculationSnapshot para aprovar.")
    approval = TechnicalApproval(
        quotation=quotation,
        approved_by=approved_by,
        crea_number=approved_by.crea_number,
        crea_state=approved_by.crea_state,
        art_number=art_number or "",
        calculation_snapshot_hash=snapshot.snapshot_hash,
        notes=notes or "",
    )
    approval.full_clean()
    approval.save()
    if request is not None:
        log_access(request, "approve", approval, {"quotation_id": quotation.pk, "snapshot_hash": snapshot.snapshot_hash})
    return approval


@transaction.atomic
def revoke_approval(approval, revoked_by, request=None):
    if approval.revoked_at is None:
        approval.revoked_at = timezone.now()
        approval.revoked_by = revoked_by
        approval.save(update_fields=["revoked_at", "revoked_by"])
        if request is not None:
            log_access(request, "revoke", approval, {"quotation_id": approval.quotation_id})
    return approval


def log_access(request, action, resource, metadata=None):
    user = getattr(request, "user", None)
    if user is not None and not user.is_authenticated:
        user = None
    return AccessLog.objects.create(
        user=user,
        action=action,
        resource_type=resource.__class__.__name__,
        resource_id=str(getattr(resource, "pk", "")),
        ip_address=(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                    or request.META.get("REMOTE_ADDR") or None),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        metadata=metadata or {},
    )
