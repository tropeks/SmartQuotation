import uuid

from django.core.exceptions import ValidationError
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class SapB1IntegrationConfig(models.Model):
    PROVIDER = "sap_b1"

    provider = models.CharField(max_length=20, default=PROVIDER, unique=True, editable=False)
    enabled = models.BooleanField(default=False)
    base_url = models.URLField(blank=True)
    company_db = models.CharField(max_length=100, blank=True)
    username = models.CharField(max_length=255, blank=True)
    password = EncryptedCharField(max_length=255, blank=True)  # cifrado em repouso
    timeout_seconds = models.PositiveIntegerField(default=30)
    sync_sales_orders_enabled = models.BooleanField(default=True)
    sync_boms_enabled = models.BooleanField(default=True)
    last_healthcheck_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_sap_b1"
        verbose_name = "Configuracao SAP B1"
        verbose_name_plural = "Configuracoes SAP B1"

    def __str__(self):
        return f"SAP B1 {self.company_db or '-'}"

    def clean(self):
        self.provider = self.PROVIDER
        duplicate_exists = (
            type(self).objects.exclude(pk=self.pk)
            .filter(provider=self.PROVIDER)
            .exists()
        )
        if duplicate_exists:
            raise ValidationError("Cada tenant suporta apenas uma configuracao SAP B1.")

    def save(self, *args, **kwargs):
        self.provider = self.PROVIDER
        self.full_clean()
        return super().save(*args, **kwargs)


class SapB1SyncBinding(models.Model):
    ENTITY_SALES_ORDER = "sales_order"
    ENTITY_BOM = "bom"
    ENTITY_CHOICES = [
        (ENTITY_SALES_ORDER, "Sales Order"),
        (ENTITY_BOM, "BOM"),
    ]
    DIRECTION_PUSH = "push"
    DIRECTION_CHOICES = [
        (DIRECTION_PUSH, "Push"),
    ]
    SOURCE_LOCAL = "smartquotation"
    SOURCE_REMOTE = "sap_b1"
    SOURCE_MIXED = "mixed"
    SOURCE_CHOICES = [
        (SOURCE_LOCAL, "SmartQuotation"),
        (SOURCE_REMOTE, "SAP B1"),
        (SOURCE_MIXED, "Mixed"),
    ]

    provider = models.CharField(max_length=20, default=SapB1IntegrationConfig.PROVIDER)
    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    local_model = models.CharField(max_length=100)
    local_id = models.CharField(max_length=50)
    remote_code = models.CharField(max_length=100, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    last_direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    source_of_truth = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MIXED)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_sap_b1"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "entity_type", "local_model", "local_id"],
                name="uniq_sap_b1_binding_local",
            ),
            models.UniqueConstraint(
                fields=["provider", "entity_type", "remote_code"],
                name="uniq_sap_b1_binding_remote_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity_type", "local_model", "local_id"]),
            models.Index(fields=["entity_type", "remote_code"]),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.local_model}:{self.local_id}"


class SapB1SyncRun(models.Model):
    DIRECTION_PUSH = "push"
    DIRECTION_CHOICES = [
        (DIRECTION_PUSH, "Push"),
    ]
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
    ENTITY_CHOICES = SapB1SyncBinding.ENTITY_CHOICES

    provider = models.CharField(max_length=20, default=SapB1IntegrationConfig.PROVIDER)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    trigger = models.CharField(max_length=30, default="manual")
    idempotency_key = models.CharField(max_length=255, unique=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    local_model = models.CharField(max_length=100, blank=True)
    local_id = models.CharField(max_length=50, blank=True)
    remote_code = models.CharField(max_length=100, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "integrations_sap_b1"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["direction", "entity_type", "status"]),
            models.Index(fields=["local_model", "local_id"]),
        ]

    def __str__(self):
        return f"{self.direction}:{self.entity_type}:{self.idempotency_key}"


class SapB1SyncAttempt(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    run = models.ForeignKey(SapB1SyncRun, on_delete=models.CASCADE, related_name="attempts")
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_sap_b1"
        ordering = ["sequence", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="uniq_sap_b1_attempt_sequence"),
        ]

    def __str__(self):
        return f"{self.run_id}#{self.sequence}"

