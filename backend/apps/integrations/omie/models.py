import uuid

from django.core.exceptions import ValidationError
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class OmieIntegrationConfig(models.Model):
    PROVIDER = "omie"

    provider = models.CharField(max_length=20, default=PROVIDER, unique=True, editable=False)
    enabled = models.BooleanField(default=False)
    app_key = EncryptedCharField(max_length=255, blank=True)    # cifrado em repouso
    app_secret = EncryptedCharField(max_length=255, blank=True)  # cifrado em repouso
    company_code = models.CharField(max_length=50, blank=True)
    environment = models.CharField(max_length=50, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=30)
    emit_on_of_completed = models.BooleanField(default=True)
    fiscal_defaults = models.JSONField(default=dict, blank=True)
    last_healthcheck_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_omie"
        verbose_name = "Configuracao Omie"
        verbose_name_plural = "Configuracoes Omie"

    def __str__(self):
        return f"Omie {self.company_code or '-'}"

    def clean(self):
        self.provider = self.PROVIDER
        duplicate_exists = (
            type(self).objects.exclude(pk=self.pk)
            .filter(provider=self.PROVIDER)
            .exists()
        )
        if duplicate_exists:
            raise ValidationError("Cada tenant suporta apenas uma configuracao Omie.")

    def save(self, *args, **kwargs):
        self.provider = self.PROVIDER
        self.full_clean()
        return super().save(*args, **kwargs)


class OmieFiscalDocument(models.Model):
    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_ISSUED = "issued"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_READY, "Ready"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_FAILED, "Failed"),
    ]

    config = models.ForeignKey(
        OmieIntegrationConfig,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fiscal_documents",
    )
    of = models.OneToOneField(
        "production.OrdemFabricacao",
        on_delete=models.PROTECT,
        related_name="omie_fiscal_document",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    remote_document_id = models.CharField(max_length=100, blank=True)
    remote_number = models.CharField(max_length=100, blank=True)
    fiscal_defaults_snapshot = models.JSONField(default=dict, blank=True)
    source_snapshot = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_omie"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["remote_document_id"]),
        ]

    def __str__(self):
        return f"NF-e {self.of.number}"


class OmieInvoiceRun(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    config = models.ForeignKey(
        OmieIntegrationConfig,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_runs",
    )
    document = models.ForeignKey(
        OmieFiscalDocument,
        on_delete=models.PROTECT,
        related_name="invoice_runs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    trigger = models.CharField(max_length=30, default="manual")
    idempotency_key = models.CharField(max_length=255, unique=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    payload = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "integrations_omie"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "started_at"]),
            models.Index(fields=["document", "status"]),
        ]

    def __str__(self):
        return f"{self.document.of.number}:{self.idempotency_key}"


class OmieInvoiceAttempt(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    run = models.ForeignKey(
        OmieInvoiceRun,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_omie"
        ordering = ["sequence", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="uniq_omie_attempt_sequence"),
        ]

    def __str__(self):
        return f"{self.run_id}#{self.sequence}"
