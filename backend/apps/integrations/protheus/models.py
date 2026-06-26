import uuid

from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class ProtheusIntegrationConfig(models.Model):
    PROVIDER = "protheus"
    AUTH_BASIC = "basic"
    AUTH_TOKEN = "token"
    AUTH_CHOICES = [
        (AUTH_BASIC, "Basic"),
        (AUTH_TOKEN, "Token"),
    ]

    provider = models.CharField(max_length=20, default=PROVIDER, unique=True)
    enabled = models.BooleanField(default=False)
    base_url = models.URLField(blank=True)
    company_code = models.CharField(max_length=20, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    environment = models.CharField(max_length=50, blank=True)
    auth_type = models.CharField(max_length=20, choices=AUTH_CHOICES, default=AUTH_BASIC)
    username = models.CharField(max_length=255, blank=True)
    password = EncryptedCharField(max_length=255, blank=True)  # cifrado em repouso
    token = EncryptedCharField(max_length=255, blank=True)     # cifrado em repouso
    timeout_seconds = models.PositiveIntegerField(default=30)
    export_on_release = models.BooleanField(default=True)
    pull_materials_enabled = models.BooleanField(default=True)
    pull_suppliers_enabled = models.BooleanField(default=True)
    pull_work_orders_enabled = models.BooleanField(default=True)
    last_healthcheck_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_protheus"
        verbose_name = "Configuracao Protheus"
        verbose_name_plural = "Configuracoes Protheus"

    def __str__(self):
        return f"Protheus {self.company_code or '-'} / {self.branch_code or '-'}"


class ProtheusSyncBinding(models.Model):
    ENTITY_WORK_ORDER = "work_order"
    ENTITY_BOM = "bom"
    ENTITY_MATERIAL = "material"
    ENTITY_SUPPLIER = "supplier"
    ENTITY_CHOICES = [
        (ENTITY_WORK_ORDER, "Work Order"),
        (ENTITY_BOM, "BOM"),
        (ENTITY_MATERIAL, "Material"),
        (ENTITY_SUPPLIER, "Supplier"),
    ]
    DIRECTION_PUSH = "push"
    DIRECTION_PULL = "pull"
    DIRECTION_CHOICES = [
        (DIRECTION_PUSH, "Push"),
        (DIRECTION_PULL, "Pull"),
    ]
    SOURCE_LOCAL = "smartquotation"
    SOURCE_REMOTE = "protheus"
    SOURCE_MIXED = "mixed"
    SOURCE_CHOICES = [
        (SOURCE_LOCAL, "SmartQuotation"),
        (SOURCE_REMOTE, "Protheus"),
        (SOURCE_MIXED, "Mixed"),
    ]

    provider = models.CharField(max_length=20, default=ProtheusIntegrationConfig.PROVIDER)
    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    local_model = models.CharField(max_length=100)
    local_id = models.CharField(max_length=50)
    remote_id = models.CharField(max_length=100, blank=True)
    remote_code = models.CharField(max_length=100, null=True, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    last_direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    source_of_truth = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MIXED)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_protheus"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "entity_type", "local_model", "local_id"],
                name="uniq_protheus_binding_local",
            ),
            models.UniqueConstraint(
                fields=["provider", "entity_type", "remote_code"],
                name="uniq_protheus_binding_remote_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity_type", "local_model", "local_id"]),
            models.Index(fields=["entity_type", "remote_code"]),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.local_model}:{self.local_id}"


class ProtheusSyncRun(models.Model):
    DIRECTION_PUSH = "push"
    DIRECTION_PULL = "pull"
    DIRECTION_CHOICES = [
        (DIRECTION_PUSH, "Push"),
        (DIRECTION_PULL, "Pull"),
    ]
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]
    ENTITY_CHOICES = ProtheusSyncBinding.ENTITY_CHOICES

    provider = models.CharField(max_length=20, default=ProtheusIntegrationConfig.PROVIDER)
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
        app_label = "integrations_protheus"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["direction", "entity_type", "status"]),
            models.Index(fields=["local_model", "local_id"]),
        ]

    def __str__(self):
        return f"{self.direction}:{self.entity_type}:{self.idempotency_key}"


class ProtheusSyncAttempt(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    run = models.ForeignKey(ProtheusSyncRun, on_delete=models.CASCADE, related_name="attempts")
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_protheus"
        ordering = ["sequence", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="uniq_protheus_attempt_sequence")
        ]


class ProtheusCatalogStaging(models.Model):
    ENTITY_MATERIAL = ProtheusSyncBinding.ENTITY_MATERIAL
    ENTITY_SUPPLIER = ProtheusSyncBinding.ENTITY_SUPPLIER
    ENTITY_CHOICES = [
        (ENTITY_MATERIAL, "Material"),
        (ENTITY_SUPPLIER, "Supplier"),
    ]
    STATUS_PENDING = "pending"
    STATUS_APPLIED = "applied"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
    ]

    provider = models.CharField(max_length=20, default=ProtheusIntegrationConfig.PROVIDER)
    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    remote_code = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    source_run = models.ForeignKey(
        ProtheusSyncRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_staging_entries",
    )
    applied_object_model = models.CharField(max_length=100, blank=True)
    applied_object_id = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="protheus_catalog_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_protheus"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "entity_type", "remote_code", "payload_hash"],
                name="uniq_protheus_catalog_staging_payload",
            )
        ]
        indexes = [
            models.Index(fields=["entity_type", "status"]),
            models.Index(fields=["remote_code", "status"]),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.remote_code}:{self.status}"


class ProtheusSupplier(models.Model):
    supplier_code = models.CharField(max_length=100, unique=True)
    legal_name = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    is_active = models.BooleanField(default=True)
    payload = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_protheus"
        ordering = ["supplier_code"]

    def __str__(self):
        return f"{self.supplier_code} - {self.legal_name}"


class ProtheusWorkOrderSnapshot(models.Model):
    remote_code = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=500, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_protheus"
        ordering = ["remote_code"]

    def __str__(self):
        return self.remote_code


class ProtheusBOMSnapshot(models.Model):
    work_order = models.OneToOneField(
        ProtheusWorkOrderSnapshot,
        on_delete=models.CASCADE,
        related_name="bom_snapshot",
    )
    payload = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_protheus"

    def __str__(self):
        return f"BOM {self.work_order.remote_code}"
