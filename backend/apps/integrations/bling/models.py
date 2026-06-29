from django.core.exceptions import ValidationError
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class BlingIntegrationConfig(models.Model):
    PROVIDER = "bling"

    provider = models.CharField(max_length=20, default=PROVIDER, unique=True, editable=False)
    enabled = models.BooleanField(default=False)
    client_id = EncryptedCharField(max_length=255, blank=True)
    client_secret = EncryptedCharField(max_length=255, blank=True)
    access_token = EncryptedCharField(max_length=2048, blank=True)
    refresh_token = EncryptedCharField(max_length=2048, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    company_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integrations_bling"
        verbose_name = "Configuracao Bling"
        verbose_name_plural = "Configuracoes Bling"

    def __str__(self):
        return f"Bling {self.company_id or '-'}"

    def clean(self):
        self.provider = self.PROVIDER
        duplicate_exists = (
            type(self).objects.exclude(pk=self.pk)
            .filter(provider=self.PROVIDER)
            .exists()
        )
        if duplicate_exists:
            raise ValidationError("Cada tenant suporta apenas uma configuracao Bling.")

    def save(self, *args, **kwargs):
        self.provider = self.PROVIDER
        self.full_clean()
        return super().save(*args, **kwargs)
