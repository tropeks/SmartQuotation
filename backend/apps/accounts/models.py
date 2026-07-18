"""
Perfis de usuário por TENANT (schema do cliente).
- UserProfile estende o User do Django (auth) com papel (role) e dados de CREA.
- Papel é uma STRING (key) que referencia uma linha de `Role` (papéis como dado, RBAC V2 M1).
- Compliance (CREA) é derivado do TRAIT `Role.requires_crea`, não do nome literal do papel
  (resolve #86). Enforcement em clean() (feedback amigável) E save() (barra create() direto).
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Role(models.Model):
    """
    Papel como DADO (por tenant). RBAC V2 M1 — desacopla compliance do nome do papel.

    A `key` é o identificador estável (== os antigos enums de UserProfile.ROLE); toda a
    resolução de permissão (matriz, cache, `user_role`) continua indexada por essa string,
    então tornar papéis dado NÃO muda o contrato de `rbac.user_role()` nem os ~30 gates de view.

    Traits desacoplam regras de domínio do nome literal:
    - `requires_crea`: papel exige CREA (era o hard-code `role=="engenheiro"` — ver #86).
    - `is_admin_like`: papel com privilégios administrativos (usado por guard-rails de M2).

    Proveniência (`is_seeded`/`source_template`/`template_version`) alimenta a UI de M2
    (papéis vindos de template vN vs. criados do zero).
    """

    key = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)

    requires_crea = models.BooleanField(default=False)
    is_admin_like = models.BooleanField(default=False)

    is_seeded = models.BooleanField(default=False)
    source_template = models.CharField(max_length=64, blank=True)
    template_version = models.PositiveIntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["key"]
        verbose_name = "papel"
        verbose_name_plural = "papéis"

    def __str__(self):
        return f"{self.name} ({self.key})"

    @classmethod
    def key_requires_crea(cls, role_key):
        """True se a role `role_key` (string) exige CREA. Fonte única do compliance CREA.

        Sem linha correspondente (tenant não semeado ou papel removido) → False (permissivo,
        nunca bloqueia indevidamente). A migração de seed garante os 5 papéis em todo schema.
        """
        if not role_key:
            return False
        return cls.objects.filter(key=role_key, requires_crea=True).exists()

    @classmethod
    def ordered(cls):
        """Papéis do tenant p/ colunas/dropdowns: built-ins na ordem canônica (a mesma
        de DEFAULT_ROLES), papéis custom depois, por nome. Fonte única da ordenação (M2)."""
        canonical = {spec["key"]: i for i, spec in enumerate(DEFAULT_ROLES)}
        roles = list(cls.objects.all())
        roles.sort(
            key=lambda r: (0, canonical[r.key]) if r.key in canonical else (1, r.name.lower())
        )
        return roles

    @classmethod
    def choices(cls):
        """[(key, name)] na ordem canônica — para ChoiceField/dropdowns dinâmicos (M2)."""
        return [(r.key, r.name) for r in cls.ordered()]


class UserProfile(models.Model):
    ROLE_VIEWER = "viewer"
    ROLE_ORCAMENTISTA = "orcamentista"
    ROLE_ENGENHEIRO = "engenheiro"
    ROLE_GESTOR_COMERCIAL = "gestor_comercial"
    ROLE_ADMIN = "admin"
    ROLE = [
        (ROLE_VIEWER, "Viewer"),
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
    must_change_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        # A antiga CheckConstraint `engenheiro_requires_crea` amarrava o CREA ao nome literal
        # do papel — quebra com papéis customizados (V2). Compliance agora vem do trait
        # `Role.requires_crea`, enforçado em clean() E save() abaixo (ver #86). Uma
        # CheckConstraint não pode referenciar trait cross-table, por isso a proteção
        # migra para a camada de aplicação (save() cobre até `objects.create()` direto).

    def _crea_missing(self):
        return Role.key_requires_crea(self.role) and not (self.crea_number or "").strip()

    def clean(self):
        """Validação de domínio: papéis com trait requires_crea precisam de CREA."""
        super().clean()
        if self._crea_missing():
            raise ValidationError({"crea_number": "Este papel requer número de CREA."})

    def save(self, *args, **kwargs):
        # Enforcement de compliance também no save() — barra `objects.create()`/`save()`
        # direto, que não passa por full_clean(). Substitui a CheckConstraint de banco.
        if self._crea_missing():
            raise ValidationError({"crea_number": "Este papel requer número de CREA."})
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.role})"


# Papéis-semente = os 5 papéis built-in do F10, agora como DADO. `key` idêntica aos antigos
# enums para preservar 100% do contrato (matriz/cache/user_role indexam por essa string).
# `requires_crea` só no engenheiro; `is_admin_like` só no admin. Espelha UserProfile.ROLE.
DEFAULT_ROLES = [
    {"key": UserProfile.ROLE_VIEWER, "name": "Viewer", "requires_crea": False, "is_admin_like": False},
    {"key": UserProfile.ROLE_ORCAMENTISTA, "name": "Orçamentista", "requires_crea": False, "is_admin_like": False},
    {"key": UserProfile.ROLE_ENGENHEIRO, "name": "Engenheiro", "requires_crea": True, "is_admin_like": False},
    {"key": UserProfile.ROLE_GESTOR_COMERCIAL, "name": "Gestor Comercial", "requires_crea": False, "is_admin_like": False},
    {"key": UserProfile.ROLE_ADMIN, "name": "Administrador", "requires_crea": False, "is_admin_like": True},
]


def seed_roles(model=None):
    """
    Semeia os 5 papéis built-in no schema atual (idempotente). Aceita `model` para uso
    em data migration (apps.get_model); usa o Role real fora de migração.

    Atualiza traits de linhas já existentes (mantém `name`/`description` custom do tenant),
    marca `is_seeded=True`. Não remove papéis custom.
    """
    Role_ = model or Role
    for spec in DEFAULT_ROLES:
        role, _created = Role_.objects.get_or_create(
            key=spec["key"],
            defaults={
                "name": spec["name"],
                "requires_crea": spec["requires_crea"],
                "is_admin_like": spec["is_admin_like"],
                "is_seeded": True,
            },
        )
        # Reafirma os traits do built-in em linhas pré-existentes (compliance é invariante);
        # preserva `name`/`description` que o tenant possa ter customizado.
        if (
            role.requires_crea != spec["requires_crea"]
            or role.is_admin_like != spec["is_admin_like"]
            or not role.is_seeded
        ):
            role.requires_crea = spec["requires_crea"]
            role.is_admin_like = spec["is_admin_like"]
            role.is_seeded = True
            role.save(update_fields=["requires_crea", "is_admin_like", "is_seeded", "updated_at"])
