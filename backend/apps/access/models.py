"""
Models do RBAC configurável (por TENANT — vivem no schema do cliente).

- RolePermission: matriz papel×capability. `allowed=True` concede a capability
  ao papel. Enforcement (T3) lê estas linhas via `role_can`. Complementa (não
  substitui) os Django Groups de `accounts.rbac`.
- ApprovalStage: estágios do fluxo de aprovação que gateiam a conversão em OF.
  `required=True` obriga o estágio; `is_builtin=True` marca estágios travados
  (ex.: aprovação técnica CREA — não desabilitável na UI).

O catálogo de capabilities (o que PODE existir) é o registry em `capabilities.py`.
Estes models guardam a CONFIGURAÇÃO (quem pode / quais estágios) por tenant.
"""
from django.conf import settings
from django.db import models

from apps.accounts.models import UserProfile


class RolePermission(models.Model):
    """Concede/nega uma capability a um papel (uma linha por par role×capability)."""

    role = models.CharField(max_length=20, choices=UserProfile.ROLE, db_index=True)
    capability = models.CharField(max_length=64, db_index=True)  # code do registry
    allowed = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        unique_together = (("role", "capability"),)
        ordering = ["capability", "role"]
        verbose_name = "permissão de papel"
        verbose_name_plural = "permissões de papel"

    def __str__(self):
        estado = "✓" if self.allowed else "✗"
        return f"{self.role} · {self.capability} {estado}"


class ApprovalStage(models.Model):
    """
    Estágio configurável do fluxo de aprovação (gate de convertibilidade).

    `is_convertible` (T7) passará a exigir todos os estágios `required=True`.
    `is_builtin` protege estágios de sistema (ex.: CREA) contra remoção/edição.
    """

    key = models.CharField(max_length=64, unique=True)  # identificador estável
    label = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0, db_index=True)
    required = models.BooleanField(default=True)
    approver_capability = models.CharField(max_length=64, blank=True)  # code do registry
    is_builtin = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["order", "key"]
        verbose_name = "estágio de aprovação"
        verbose_name_plural = "estágios de aprovação"

    def __str__(self):
        return f"{self.order}. {self.label}" + (" [builtin]" if self.is_builtin else "")
