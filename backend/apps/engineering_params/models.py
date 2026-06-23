"""
Parâmetros de engenharia (TENANT schema) — editáveis pelo tenant, alimentam o motor de custeio.

Separação-chave (insight @WellToMcAt):
- ProcessParameter (FÍSICA): gera HORAS — avanços/taxas/tempos por (operação × método/máquina).
- Rate (CUSTO): converte HORAS → R$ — rate_hh (homem-hora) e rate_hm (hora-máquina) por operação.
- TenantParamConfig: knobs globais do tenant (fator_correcao_mo, limiar radial/CNC).

Tudo versionado por valid_from (vigência). Ver pricing_engine/{rates.py,process_params.py}.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.db import models


class RateManager(models.Manager):
    def vigente(self, operacao, on_date=None):
        """Retorna o Rate vigente para a operação numa data (default: hoje), ou None.

        Vigente = valid_from <= on_date e (valid_until nulo ou >= on_date).
        Em caso de sobreposição, vence o de valid_from mais recente.
        """
        on_date = on_date or date.today()
        return (
            self.get_queryset()
            .filter(operacao=operacao, valid_from__lte=on_date)
            .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=on_date))
            .order_by("-valid_from")
            .first()
        )


class Rate(models.Model):
    """Custo de mão de obra por operação. rate_hh = R$/hora homem-hora; rate_hm = R$/hora máquina."""

    operacao = models.CharField(max_length=100, db_index=True)          # ex: FURAR_ESPELHO
    rate_hh = models.DecimalField(max_digits=10, decimal_places=2)      # R$/hora homem-hora
    rate_hm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # R$/hora máquina
    valid_from = models.DateField(default=date.today)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RateManager()

    class Meta:
        ordering = ["operacao", "-valid_from"]
        indexes = [models.Index(fields=["operacao", "valid_from"])]
        constraints = [
            models.UniqueConstraint(
                fields=["operacao", "valid_from"], name="uniq_rate_operacao_valid_from"
            )
        ]

    def vigente(self, on_date=None):
        """Atalho de instância: o Rate vigente desta operação na data dada."""
        return Rate.objects.vigente(self.operacao, on_date)

    def __str__(self):
        return f"{self.operacao} @ {self.valid_from} (HH={self.rate_hh})"


class ProcessParameter(models.Model):
    """Parâmetro físico (avanço/taxa/tempo) por (operação × método). valor nulo = pendente (CNC)."""

    METODO = [("radial", "Radial"), ("cnc", "CNC"), ("manual", "Manual")]
    UNIDADE = [
        ("mm/min", "mm/min"),
        ("min/furo", "min/furo"),
        ("min/tubo", "min/tubo"),
        ("juntas/h", "juntas/h"),
        ("tubos/h", "tubos/h"),
        ("fator", "fator"),
    ]

    operacao = models.CharField(max_length=100, db_index=True)          # ex: FURAR_ESPELHO
    metodo = models.CharField(max_length=20, choices=METODO)            # radial | cnc | manual
    valor = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)  # None = pendente
    unidade = models.CharField(max_length=20, choices=UNIDADE)
    descricao = models.CharField(max_length=255, blank=True)
    valid_from = models.DateField(default=date.today)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["operacao", "metodo", "-valid_from"]
        indexes = [models.Index(fields=["operacao", "metodo", "valid_from"])]
        constraints = [
            models.UniqueConstraint(
                fields=["operacao", "metodo", "valid_from"],
                name="uniq_processparam_op_metodo_valid_from",
            )
        ]

    def __str__(self):
        v = "PENDENTE" if self.valor is None else f"{self.valor} {self.unidade}"
        return f"{self.operacao} [{self.metodo}] = {v}"


class TenantParamConfig(models.Model):
    """Knobs globais do tenant (singleton). fator_correcao_mo multiplica TODAS as horas (B31)."""

    fator_correcao_mo = models.DecimalField(max_digits=6, decimal_places=4, default=1.0)
    drill_method_threshold_holes = models.IntegerField(default=600)  # limiar radial→CNC na furação
    # compatibilidade entre letras TEMA: block (impede) | warn (avisa) | free (livre)
    tema_compat_mode = models.CharField(
        max_length=10, default="warn",
        choices=[("block", "Bloquear"), ("warn", "Avisar"), ("free", "Livre")])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant param config"
        verbose_name_plural = "Tenant param config"

    @classmethod
    def get_solo(cls):
        """Retorna (criando se preciso) a única linha de config do tenant."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1  # garante singleton
        super().save(*args, **kwargs)

    def __str__(self):
        return f"TenantParamConfig(mo={self.fator_correcao_mo}, threshold={self.drill_method_threshold_holes})"


class RateSuggestion(models.Model):
    STATUS = [('pending','Pendente'),('accepted','Aplicada'),('dismissed','Descartada')]
    operacao = models.CharField(max_length=100, db_index=True)
    actual_mean_rate = models.DecimalField(max_digits=14, decimal_places=6)
    current_rate_hh = models.DecimalField(max_digits=10, decimal_places=2)
    delta_pct = models.DecimalField(max_digits=7, decimal_places=2)
    n_samples = models.PositiveIntegerField()
    confidence = models.DecimalField(max_digits=5, decimal_places=4)
    status = models.CharField(max_length=20, choices=STATUS, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['operacao'],
                condition=models.Q(status='pending'),
                name='uniq_suggestion_pending_por_operacao'
            )
        ]

    def __str__(self):
        return f'{self.operacao} Δ{self.delta_pct}% N={self.n_samples} [{self.status}]'
