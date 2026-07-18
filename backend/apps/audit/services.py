"""Serviços de auditoria H1."""
from django.contrib.auth import authenticate
from django.core.mail import EmailMessage
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, UserProfile
from apps.audit.models import AccessLog, ApprovalRequest, TechnicalApproval


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


@transaction.atomic
def request_remote_approval(quotation, requested_by, notes="", request=None):
    snapshot = latest_snapshot_for(quotation)
    approval_request = ApprovalRequest.objects.create(
        quotation=quotation,
        requested_by=requested_by,
        request_type=ApprovalRequest.TYPE_REMOTE,
        snapshot_hash=snapshot.snapshot_hash if snapshot is not None else "",
        notes=notes or "",
        notified_at=timezone.now(),
    )
    # Destinatários = papéis que assinam o estágio técnico (trait requires_crea, desacoplado
    # do nome — ver #86) + o gestor comercial. Para o tenant default, requires_crea == {engenheiro},
    # então o conjunto é idêntico ao antigo hard-code. O alvo por capability-do-estágio-corrente
    # (fim do #86) é trabalho de M4/M5; aqui só removemos o acoplamento ao nome literal do papel.
    crea_role_keys = list(Role.objects.filter(requires_crea=True).values_list("key", flat=True))
    notify_roles = crea_role_keys + [UserProfile.ROLE_GESTOR_COMERCIAL]
    recipients = list(
        UserProfile.objects.filter(
            is_active=True,
            role__in=notify_roles,
            user__email__gt="",
        )
        .select_related("user")
        .values_list("user__email", flat=True)
        .distinct()
    )
    if recipients:
        EmailMessage(
            subject=f"[SmartQuotation] Aprovação técnica solicitada para {quotation.number}",
            body=(
                f"Cotação: {quotation.number}\n"
                f"Título: {quotation.title}\n"
                f"Solicitante: {requested_by.full_name}\n"
                f"Observações: {notes or '-'}"
            ),
            to=recipients,
        ).send(fail_silently=False)
    if request is not None:
        log_access(request, "approve", approval_request, {
            "quotation_id": quotation.pk,
            "snapshot_hash": approval_request.snapshot_hash,
            "request_type": approval_request.request_type,
            "result": "remote_requested",
        })
    return approval_request


def _log_approval_attempt(request, quotation, approver_profile, result, reason):
    if request is None:
        return None
    return log_access(request, "approve", quotation, {
        "quotation_id": quotation.pk,
        "approved_by_profile_id": getattr(approver_profile, "pk", None),
        "result": result,
        "reason": reason,
    })


def approve_presencial(quotation, approver_profile, password, request=None, art_number="", notes=""):
    if approver_profile is None:
        _log_approval_attempt(request, quotation, approver_profile, "denied", "invalid_approver")
        raise ValidationError("Nao foi possivel validar a aprovacao.")
    if not Role.key_requires_crea(approver_profile.role) or not (approver_profile.crea_number or "").strip():
        _log_approval_attempt(request, quotation, approver_profile, "denied", "invalid_approver")
        raise ValidationError("Nao foi possivel validar a aprovacao.")
    authenticated = authenticate(
        request=request,
        username=approver_profile.user.username,
        password=password,
    )
    if authenticated is None or authenticated.pk != approver_profile.user_id:
        if not approver_profile.user.check_password(password):
            _log_approval_attempt(request, quotation, approver_profile, "denied", "invalid_credentials")
            raise ValidationError("Nao foi possivel validar a aprovacao.")
    with transaction.atomic():
        approval = approve_quotation(
            quotation,
            approver_profile,
            art_number=art_number,
            notes=notes,
            request=None,
        )
        ApprovalRequest.objects.filter(
            quotation=quotation,
            status=ApprovalRequest.STATUS_PENDING,
        ).update(status=ApprovalRequest.STATUS_APPROVED, resolved_at=timezone.now())
    if request is not None:
        log_access(request, "approve", approval, {
            "quotation_id": quotation.pk,
            "snapshot_hash": approval.calculation_snapshot_hash,
            "approved_by_profile_id": approver_profile.pk,
            "result": "success",
        })
    return approval
