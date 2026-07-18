"""
Parâmetros de engenharia (TENANT schema) — editáveis pelo tenant, alimentam o motor de custeio.

Separação-chave (insight @WellToMcAt):
- ProcessParameter (FÍSICA): gera HORAS — avanços/taxas/tempos por (operação × método/máquina × material).
- Rate (CUSTO): converte HORAS → R$ — rate_hh (homem-hora) e rate_hm (hora-máquina) por operação.
- TenantParamConfig: knobs globais do tenant (fator_correcao_mo, limiar radial/CNC).

Tudo versionado por valid_from (vigência). Ver pricing_engine/{rates.py,process_params.py}.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class RateManager(models.Manager):
    def vigente(self, operacao, on_date=None):
        """Retorna o Rate vigente para a operação numa data (default: hoje), ou None.

        Vigente = valid_from <= on_date e (valid_until nulo ou >= on_date).
        Em caso de sobreposição, vence o de valid_from mais recente.
        """
        on_date = on_date or timezone.now().date()
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


class ProcessParameterManager(models.Manager):
    def vigente(self, operacao, metodo, material=None, on_date=None):
        """Retorna o ProcessParameter vigente por operação+metodo+material.

        Regra de precedência:
        1. material específico vigente
        2. fallback com material NULL vigente

        Se `material` vier vazio/None, mantém o comportamento atual e procura apenas
        o fallback NULL.
        """
        on_date = on_date or timezone.now().date()
        material = material or None
        base = (
            self.get_queryset()
            .filter(operacao=operacao, metodo=metodo, valid_from__lte=on_date)
            .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=on_date))
        )
        if material is not None:
            specific = (
                base.filter(material=material)
                .order_by("-valid_from")
                .first()
            )
            if specific is not None:
                return specific
        return (
            base.filter(material__isnull=True)
            .order_by("-valid_from")
            .first()
        )


class ProcessParameter(models.Model):
    """Parâmetro físico (avanço/taxa/tempo) por (operação × método × material)."""

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
    material = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    valor = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)  # None = pendente
    unidade = models.CharField(max_length=20, choices=UNIDADE)
    descricao = models.CharField(max_length=255, blank=True)
    valid_from = models.DateField(default=date.today)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProcessParameterManager()

    class Meta:
        ordering = ["operacao", "metodo", "material", "-valid_from"]
        indexes = [models.Index(fields=["operacao", "metodo", "material", "valid_from"])]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(operacao="ALARGAR_ESPELHO", metodo="cnc"),
                name="ck_processparam_sem_alargar_espelho_cnc",
            ),
            models.UniqueConstraint(
                fields=["operacao", "metodo", "valid_from"],
                condition=models.Q(material__isnull=True),
                name="uniq_processparam_op_metodo_valid_from_null_material",
            ),
            models.UniqueConstraint(
                fields=["operacao", "metodo", "material", "valid_from"],
                condition=models.Q(material__isnull=False),
                name="uniq_processparam_op_metodo_material_valid_from",
            )
        ]

    def __str__(self):
        v = "PENDENTE" if self.valor is None else f"{self.valor} {self.unidade}"
        material = f" / {self.material}" if self.material else ""
        return f"{self.operacao} [{self.metodo}{material}] = {v}"

    def save(self, *args, **kwargs):
        self.material = self.material or None
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.operacao == "ALARGAR_ESPELHO" and self.metodo == "cnc":
            raise ValidationError("ALARGAR_ESPELHO não existe como etapa em CNC.")


def _default_tube_standard_lengths() -> list:
    """Comprimentos comerciais de tubo padrão (mm). ENGEMATEX: 6,10 m e 12 m."""
    return [6100, 12000]


def _default_perda_por_familia() -> dict:
    """Scrap (fator bruto/líquido) por família geométrica — semeia do default do motor
    (pricing_engine.beu_geometry.PERDA_POR_FAMILIA, os valores do Wellington). É o PONTO DE
    PARTIDA editável do tenant; o motor lê o override via TenantCostChain.perda_por_familia
    (Config de Engenharia V2 / F1). Import tardio p/ não acoplar o load do model ao motor."""
    from pricing_engine.beu_geometry import PERDA_POR_FAMILIA
    return dict(PERDA_POR_FAMILIA)


def _default_setup_frac() -> dict:
    """Fração de setup fixo por parâmetro físico — semeia do default do motor
    (pricing_engine.permutador_quote._SETUP_FRAC). Editável pelo tenant; o motor lê o override via
    TenantCostChain.setup_frac e escala as HORAS no caminho paramétrico (razão≠1). Import tardio.
    NOTA p/ UI (PR-C): é o setup do MODELO paramétrico (escala horas por driver físico), DISTINTO
    do ComponentOperation.setup_fixo (setup por operação no roteiro de partes) — nomear separado."""
    from pricing_engine.permutador_quote import _SETUP_FRAC
    return dict(_SETUP_FRAC)


class TenantParamConfig(models.Model):
    """Knobs globais do tenant (singleton). fator_correcao_mo multiplica TODAS as horas (B31)."""

    fator_correcao_mo = models.DecimalField(max_digits=6, decimal_places=4, default=1.0)
    drill_method_threshold_holes = models.IntegerField(default=600)  # limiar radial→CNC na furação
    # compatibilidade entre letras TEMA: block (impede) | warn (avisa) | free (livre)
    tema_compat_mode = models.CharField(
        max_length=10, default="warn",
        choices=[("block", "Bloquear"), ("warn", "Avisar"), ("free", "Livre")])
    # C1 — corte de chicana (baffle cut) padrão em % do Ø interno do casco. O motor consome
    # mm (hc = OD − corte); o % é convertido para mm no front/form. Default TEMA ~25%.
    baffle_cut_default_pct = models.DecimalField(max_digits=5, decimal_places=2, default=25.0)
    # C2 — comprimentos comerciais de tubo padrão (mm). Lista editável; entrada livre continua.
    tube_standard_lengths_mm = models.JSONField(default=_default_tube_standard_lengths)
    # C3 — raio mínimo da curva em U = fator × OD do tubo (TEMA RCB-2.3, default 1,5×OD).
    u_bend_min_radius_factor = models.DecimalField(max_digits=5, decimal_places=2, default=1.5)
    # V2/F1 — scrap por família {família: fator bruto/líquido}. Override do PERDA_POR_FAMILIA do
    # motor; o adapter copia p/ TenantCostChain.perda_por_familia. Só afeta o custeio no caminho
    # com dims_override (data sheet); a referência/gate 0,0% não lê perda (ver PLAN F1 do motor).
    perda_por_familia = models.JSONField(default=_default_perda_por_familia)
    # V2/F1 — setup fixo por parâmetro {param: fração 0..1}. Override do _SETUP_FRAC do motor; o
    # adapter copia p/ TenantCostChain.setup_frac. Escala horas no caminho paramétrico (razão≠1) →
    # move o custeio do data sheet real. No referência (razão 1,0) o setup se cancela (gate 0,0%).
    setup_frac = models.JSONField(default=_default_setup_frac)
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
