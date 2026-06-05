"""
Perfis de usuário por TENANT (schema do cliente).
- UserProfile estende o User do Django (auth) com papel (role) e dados de CREA.
- Regra de negócio: engenheiro EXIGE número de CREA (clean() + CheckConstraint).
  A constraint garante a regra no banco; clean() dá feedback amigável no form/admin.
"""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UserProfile(models.Model):
    ROLE_ORCAMENTISTA = "orcamentista"
    ROLE_ENGENHEIRO = "engenheiro"
    ROLE_GESTOR_COMERCIAL = "gestor_comercial"
    ROLE_ADMIN = "admin"
    ROLE = [
        (ROLE_ORCAMENTISTA, "Orçamentista"),
        (ROLE_ENGENHEIRO, "Engenheiro"),
        (ROLE_GESTOR_COMERCIAL, "Gestor Comercial"),
        (ROLE_ADMIN, "Admin"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE, default=ROLE_ORCAMENTISTA, db_index=True)
    crea_number = models.CharField(max_length=30, blank=True)       # obrigatório p/ engenheiro
    crea_state = models.CharField(max_length=2, blank=True)         # UF do registro (ex: SP)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            # Engenheiro só é válido com CREA preenchido (regra reforçada no banco).
            models.CheckConstraint(
                name="engenheiro_requires_crea",
                condition=~Q(role="engenheiro") | ~Q(crea_number=""),
            ),
        ]

    def clean(self):
        """Validação de domínio: engenheiro precisa de CREA."""
        super().clean()
        if self.role == self.ROLE_ENGENHEIRO and not (self.crea_number or "").strip():
            raise ValidationError({"crea_number": "Engenheiro requer número de CREA."})

    def __str__(self):
        return f"{self.full_name} ({self.role})"
