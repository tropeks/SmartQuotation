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


class ApprovalWorkflow(models.Model):
    """
    Fluxo de aprovação de um `action_type` (RBAC V2 M3). Na V2.0 só existe
    `of.convert` (conversão de cotação em OF) — 1 workflow por tenant (action_type único).

    Agrupa `ApprovalStage`s ordenados. `is_active=False` = fluxo desligado (cai no
    comportamento built-in mínimo). `source_template` guarda de qual WorkflowTemplate
    (código) o fluxo foi montado (proveniência para a UI).
    """

    ACTION_OF_CONVERT = "of.convert"
    ACTION_CHOICES = [(ACTION_OF_CONVERT, "Conversão em OF")]

    action_type = models.CharField(
        max_length=32, choices=ACTION_CHOICES, default=ACTION_OF_CONVERT, unique=True
    )
    name = models.CharField(max_length=120, default="Conversão em Ordem de Fabricação")
    is_active = models.BooleanField(default=True)
    source_template = models.CharField(max_length=64, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        verbose_name = "fluxo de aprovação"
        verbose_name_plural = "fluxos de aprovação"

    def __str__(self):
        return f"{self.name} ({self.action_type})"


class ApprovalStage(models.Model):
    """
    Estágio configurável do fluxo de aprovação (gate de convertibilidade).

    `is_convertible` (T7) passará a exigir todos os estágios `required=True`.
    `is_builtin` protege estágios de sistema (ex.: CREA) contra remoção/edição.
    `workflow` (M3) agrupa estágios por fluxo; null = estágio legado (pré-M3),
    tratado como pertencente ao fluxo default de conversão.
    """

    key = models.CharField(max_length=64, unique=True)  # identificador estável
    label = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0, db_index=True)
    required = models.BooleanField(default=True)
    approver_capability = models.CharField(max_length=64, blank=True)  # code do registry
    is_builtin = models.BooleanField(default=False)
    workflow = models.ForeignKey(
        ApprovalWorkflow, null=True, blank=True,
        on_delete=models.CASCADE, related_name="stages",
    )

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
