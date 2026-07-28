"""
Estrutura de custo do tenant — a metade que faltava do custeio por capacidade.

O `ProcessParameter` já é a equação de tempo do TDABC (física → horas). O que não
existia era a **taxa de custo da capacidade**:

    custo da capacidade fornecida (R$/mês)  ÷  capacidade prática (h/mês)

Sem esse denominador, o R$/hora do sistema vem de benchmark — o preço que o mercado
pratica, não o custo que a fábrica tem. É a diferença entre "bate com o que a empresa
cotaria" e "prova que o preço cobre a operação".

VERSIONADA POR VIGÊNCIA, mesmo padrão de `Rate`/`ProcessParameter`: o cliente troca de
galpão, muda o turno, contrata — e o custo/hora muda junto. Mas uma cotação feita em
março tem de continuar reproduzindo o custo/hora de março, então nada é sobrescrito.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class CostStructureManager(models.Manager):
    def vigente(self, on_date=None):
        """A estrutura vigente numa data (default: hoje), ou None.

        Vigente = valid_from <= on_date e (valid_until nulo ou >= on_date).
        Em sobreposição, vence o de valid_from mais recente — idêntico a
        `RateManager.vigente` (apps/engineering_params/models.py:19).
        """
        on_date = on_date or timezone.now().date()
        return (
            self.get_queryset()
            .filter(valid_from__lte=on_date)
            .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=on_date))
            .order_by("-valid_from", "-id")
            .first()
        )


class CostStructure(models.Model):
    """Um retrato do custo da capacidade da empresa, com vigência."""

    D0 = Decimal("0")

    # ── de onde veio ───────────────────────────────────────────────────────────
    ORIGEM = [
        ("formulario", "Formulário externo"),
        ("manual", "Digitada no sistema"),
        ("importada", "Importada de arquivo"),
    ]
    origem = models.CharField(max_length=20, choices=ORIGEM, default="manual")
    empresa = models.CharField(max_length=255, blank=True)
    respondente = models.CharField(max_length=255, blank=True)
    mes_referencia = models.CharField(max_length=7, blank=True, help_text="AAAA-MM")

    # ── custo da capacidade fornecida (R$/mês) ─────────────────────────────────
    # Separados por bloco porque a abertura é o que ensina o cliente onde o dinheiro
    # está — um total único esconde justamente o custo indireto, que é onde a margem
    # some sem deixar rastro.
    custo_pessoal_direto = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    custo_pessoal_indireto = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    custo_galpao = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    custo_maquinas = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    custo_estrutura = models.DecimalField(max_digits=14, decimal_places=2, default=D0,
                                          help_text="Já rateado pelo percentual aplicável")

    # ── capacidade prática (h/mês) ─────────────────────────────────────────────
    pessoas_produtivas = models.DecimalField(max_digits=8, decimal_places=2, default=D0,
                                             help_text="Só quem fabrica; indiretos não vendem hora")
    jornada_semanal_h = models.DecimalField(max_digits=6, decimal_places=2,
                                            default=Decimal("44"))
    semanas_mes = models.DecimalField(max_digits=5, decimal_places=2,
                                      default=Decimal("4.33"))
    fator_pratico_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("82"),
        help_text="Quanto da jornada vira produção. Prática consolidada: 80–85%")
    horas_extras_mes = models.DecimalField(max_digits=8, decimal_places=2, default=D0)

    # ── a régua atual, para comparação ─────────────────────────────────────────
    rate_praticado = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="R$/h de mão de obra que a empresa cobra hoje")

    # ── vigência (padrão de Rate/ProcessParameter) ─────────────────────────────
    valid_from = models.DateField(default=date.today)
    valid_until = models.DateField(null=True, blank=True)

    payload = models.JSONField(default=dict, blank=True,
                               help_text="Resposta crua, para recomputar se a fórmula mudar")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CostStructureManager()

    class Meta:
        ordering = ["-valid_from", "-id"]
        verbose_name = "estrutura de custo"
        verbose_name_plural = "estruturas de custo"
        constraints = [
            models.UniqueConstraint(fields=["valid_from"],
                                    name="unique_cost_structure_valid_from"),
        ]

    def __str__(self):
        return f"Estrutura de custo desde {self.valid_from:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({"valid_until": "A vigência não pode terminar antes de começar."})
        if self.fator_pratico_pct is not None and not (0 < self.fator_pratico_pct <= 100):
            raise ValidationError(
                {"fator_pratico_pct": "O fator de capacidade prática fica entre 0 e 100%."})

    # ── a conta ────────────────────────────────────────────────────────────────
    @property
    def custo_mensal(self):
        """Custo da capacidade fornecida: tudo que se paga para manter a fábrica aberta."""
        return (self.custo_pessoal_direto + self.custo_pessoal_indireto
                + self.custo_galpao + self.custo_maquinas + self.custo_estrutura)

    @property
    def horas_teoricas(self):
        return self.pessoas_produtivas * self.jornada_semanal_h * self.semanas_mes

    @property
    def horas_mes(self):
        """Capacidade prática: ninguém produz 100% da jornada.

        DDS, café, buscar material, esperar ponte rolante, reunião, limpeza. O TDABC
        trabalha com 80–85% da jornada; aqui o fator é do tenant, com esse default.
        """
        return (self.horas_teoricas * self.fator_pratico_pct / Decimal("100")
                + self.horas_extras_mes)

    @property
    def custo_hora(self):
        """R$/hora real. None quando ainda não há capacidade informada."""
        horas = self.horas_mes
        if horas <= 0:
            return None
        return (self.custo_mensal / horas).quantize(Decimal("0.0001"))

    @property
    def ponto_equilibrio_horas(self):
        """Quantas horas/mês precisam ser vendidas ao rate praticado para pagar a fábrica."""
        if not self.rate_praticado or self.rate_praticado <= 0:
            return None
        return (self.custo_mensal / self.rate_praticado).quantize(Decimal("0.01"))

    def encerrar_em(self, quando):
        """Fecha esta vigência na véspera de `quando` (abrir a próxima é do chamador)."""
        from datetime import timedelta

        self.valid_until = quando - timedelta(days=1)
        self.save(update_fields=["valid_until"])
        return self
