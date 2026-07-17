"""Auditabilidade H1: aprovação técnica e log mínimo de ações sensíveis."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TechnicalApproval(models.Model):
    """Aprovação técnica vinculada ao snapshot de cálculo de uma cotação.

    H1: CREA obrigatório no UserProfile do aprovador; ART opcional. Revogação é lógica.
    """

    quotation = models.ForeignKey(
        "quotations.Quotation", on_delete=models.CASCADE, related_name="technical_approvals")
    approved_by = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.PROTECT, related_name="technical_approvals")
    crea_number = models.CharField(max_length=50)
    crea_state = models.CharField(max_length=2, blank=True)
    art_number = models.CharField(max_length=100, blank=True)
    calculation_snapshot_hash = models.CharField(max_length=64, db_index=True)
    notes = models.TextField(blank=True)
    approved_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "accounts.UserProfile", null=True, blank=True, on_delete=models.PROTECT,
        related_name="revoked_technical_approvals")

    class Meta:
        ordering = ["-approved_at"]
        indexes = [models.Index(fields=["quotation", "approved_at"])]

    @property
    def is_active(self):
        return self.revoked_at is None

    def clean(self):
        super().clean()
        profile = self.approved_by
        if not profile:
            return
        if profile.role != "engenheiro":
            raise ValidationError({"approved_by": "Aprovação técnica exige perfil engenheiro."})
        if not (profile.crea_number or "").strip():
            raise ValidationError({"crea_number": "Aprovação técnica exige CREA do engenheiro."})

    def save(self, *args, **kwargs):
        if self.approved_by_id and not self.crea_number:
            self.crea_number = self.approved_by.crea_number
        if self.approved_by_id and not self.crea_state:
            self.crea_state = self.approved_by.crea_state
        super().save(*args, **kwargs)


class ApprovalRequest(models.Model):
    """Solicitação de aprovação técnica ainda não atendida."""

    TYPE_REMOTE = "remote"
    TYPE_PRESENTIAL = "presential"
    TYPE_CHOICES = [
        (TYPE_REMOTE, "Remota"),
        (TYPE_PRESENTIAL, "Presencial"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_APPROVED, "Aprovada"),
        (STATUS_CANCELLED, "Cancelada"),
    ]

    quotation = models.ForeignKey(
        "quotations.Quotation", on_delete=models.CASCADE, related_name="approval_requests")
    requested_by = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.PROTECT, related_name="approval_requests")
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_REMOTE)
    snapshot_hash = models.CharField(max_length=64, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["quotation", "status", "created_at"])]


class AccessLog(models.Model):
    """Log append-only de ações sensíveis. H1 não implementa hash-chain."""

    ACTION_CHOICES = [
        ("view", "View"),
        ("download", "Download"),
        ("generate", "Generate"),
        ("approve", "Approve"),
        ("revoke", "Revoke"),
        ("convert", "Convert"),
        ("transition", "Transition"),
        ("appoint", "Appoint"),
        ("itp_generate", "ITP Generate"),
        ("itp_accept", "ITP Accept"),
        ("edit", "Edit"),
        ("rate_change", "Rate Change"),
        ("param_change", "Param Change"),
        ("role_change", "Role Change"),
        ("member_deactivate", "Member Deactivate"),
        ("permission_change", "Permission Change"),
        ("approval_config_change", "Approval Config Change"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="access_logs")
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "resource_type", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]
