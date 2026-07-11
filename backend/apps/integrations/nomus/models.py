from django.core.exceptions import ValidationError
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class NomusIntegrationConfig(models.Model):
    PROVIDER = "nomus"

    provider = models.CharField(max_length=20, default=PROVIDER, unique=True, editable=False)
    enabled = models.BooleanField(default=False)
    auto_export = models.BooleanField(default=False)
    base_url = models.URLField(blank=True)
    username = EncryptedCharField(max_length=255, blank=True)
    access_key = EncryptedCharField(max_length=255, blank=True)
    password = EncryptedCharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_nomus"
        verbose_name = "Configuracao Nomus"
        verbose_name_plural = "Configuracoes Nomus"

    def __str__(self):
        return f"Nomus {self.base_url or '-'}"

    def clean(self):
        self.provider = self.PROVIDER
        duplicate_exists = (
            type(self).objects.exclude(pk=self.pk)
            .filter(provider=self.PROVIDER)
            .exists()
        )
        if duplicate_exists:
            raise ValidationError("Cada tenant suporta apenas uma configuracao Nomus.")

    def save(self, *args, **kwargs):
        self.provider = self.PROVIDER
        self.full_clean()
        return super().save(*args, **kwargs)


class NomusSyncRun(models.Model):
    DIRECTION_PUSH = "push"
    DIRECTION_CHOICES = [
        (DIRECTION_PUSH, "Push"),
    ]
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]
    ENTITY_PRODUCTION_ORDER = "production_order"
    ENTITY_BOM = "bom"
    ENTITY_ROUTING = "routing"
    ENTITY_CHOICES = [
        (ENTITY_PRODUCTION_ORDER, "Production Order"),
        (ENTITY_BOM, "BOM"),
        (ENTITY_ROUTING, "Routing"),
    ]

    provider = models.CharField(max_length=20, default=NomusIntegrationConfig.PROVIDER)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    entity_type = models.CharField(max_length=30, choices=ENTITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integrations_nomus"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["direction", "entity_type", "status"]),
        ]

    def __str__(self):
        return f"{self.direction}:{self.entity_type}:{self.status}"


class NomusExportLog(models.Model):
    STATUS_PENDING = "pending"
    STATUS_EXPORTED = "exported"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_EXPORTED, "Exported"),
        (STATUS_ERROR, "Error"),
    ]

    sync_run = models.OneToOneField(
        NomusSyncRun,
        on_delete=models.CASCADE,
        related_name="export_log",
        null=True,
        blank=True,
    )
    remote_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    conflict = models.BooleanField(default=False)
    conflict_reason = models.TextField(blank=True)
    retry = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_nomus"
        verbose_name = "Nomus Export Log"
        verbose_name_plural = "Nomus Export Logs"
        indexes = [
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"NomusExportLog:{self.remote_id}:{self.status}"
