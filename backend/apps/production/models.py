"""Modelos de Ordem de Fabricação (H2.1)."""
from decimal import Decimal

from django.conf import settings
from django.db import models

STATUS_ABERTA = "aberta"
STATUS_LIBERADA = "liberada"
STATUS_EM_PRODUCAO = "em_producao"
STATUS_CONCLUIDA = "concluida"
STATUS_CANCELADA = "cancelada"

STATUS = [
    (STATUS_ABERTA, "Aberta"),
    (STATUS_LIBERADA, "Liberada"),
    (STATUS_EM_PRODUCAO, "Em Produção"),
    (STATUS_CONCLUIDA, "Concluída"),
    (STATUS_CANCELADA, "Cancelada"),
]

# Espelha quotations.Quotation.SCOPE (denormalizado no snapshot da OF)
SCOPE = [("tube_bundle", "Feixe Tubular"), ("complete", "Equipamento Completo")]


class OrdemFabricacao(models.Model):
    number = models.CharField(max_length=50, unique=True)
    quotation = models.ForeignKey(
        "quotations.Quotation", on_delete=models.PROTECT, related_name="ordens_fabricacao")
    quotation_number = models.CharField(max_length=50)
    quotation_revision = models.PositiveSmallIntegerField(default=0)
    calculation_snapshot = models.ForeignKey(
        "quotations.CalculationSnapshot", on_delete=models.PROTECT, related_name="ordens_fabricacao")
    snapshot_hash = models.CharField(max_length=64, db_index=True)
    customer_name = models.CharField(max_length=255)
    title = models.CharField(max_length=500)
    scope = models.CharField(max_length=20, choices=SCOPE)
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_ABERTA)
    custo_material = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_mo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    preco_com_impostos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    peso_bruto_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    peso_liquido_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ordens_fabricacao")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    released_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ofs_liberadas")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ofs_iniciadas")
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ofs_concluidas")
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ofs_canceladas")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["quotation", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["quotation"],
                condition=~models.Q(status=STATUS_CANCELADA),
                name="uniq_active_of_per_quotation",
            ),
        ]

    def __str__(self):
        return f"{self.number} — {self.title}"

    @property
    def hour_variance_observations(self):
        """SQ-COST-4: observações de horas (SQ-COST-3) ordenadas por |delta_horas_pct|
        desc — maior desvio primeiro. Observações sem base de horas (delta_horas_pct=None,
        operação de valor fixo) ficam por último. Somente leitura/apresentação: não
        recalcula estimated_hh/delta_horas_pct (isso é feito em
        services._close_out_observations, SQ-COST-3 — não tocado aqui)."""
        def _abs_delta(obs):
            return abs(obs.delta_horas_pct) if obs.delta_horas_pct is not None else Decimal("-1")
        return sorted(self.observations.all(), key=_abs_delta, reverse=True)


class OFItem(models.Model):
    ordem = models.ForeignKey("OrdemFabricacao", on_delete=models.CASCADE, related_name="itens")
    codigo_item = models.CharField(max_length=30)
    descricao = models.CharField(max_length=255)
    custo_material = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_mo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sort_order = models.PositiveSmallIntegerField(default=0)
    source_item_id = models.PositiveIntegerField(null=True, blank=True)  # provenance only, NOT a FK

    class Meta:
        ordering = ["sort_order", "codigo_item"]

    @property
    def custo_total(self):
        return self.custo_material + self.custo_mo


class OFMaterial(models.Model):
    item = models.ForeignKey("OFItem", on_delete=models.CASCADE, related_name="materiais")
    codigo_mp = models.CharField(max_length=30)
    descricao = models.CharField(max_length=255)
    material = models.CharField(max_length=50)
    forma = models.CharField(max_length=20)
    peso_bruto_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    peso_liquido_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    preco_kgf = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    custo = models.DecimalField(max_digits=14, decimal_places=2, default=0)


class OFOperation(models.Model):
    item = models.ForeignKey("OFItem", on_delete=models.CASCADE, related_name="operacoes")
    codigo_op = models.CharField(max_length=40)
    descricao = models.CharField(max_length=255)
    metodo = models.CharField(max_length=20, blank=True)
    custo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    horas_hh = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    horas_hm = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    taxa_hora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxa_hora_hm = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    custo_direto = models.BooleanField(default=True)
    aplicavel = models.BooleanField(default=True)
    sequence = models.PositiveSmallIntegerField(default=0)

    def recalc_custo(self):
        if self.custo_direto:
            return self.custo

        self.custo = (self.horas_hh * self.taxa_hora) + (self.horas_hm * self.taxa_hora_hm)
        if self.pk:
            self.save(update_fields=["custo"])
        return self.custo

    @property
    def actual_hh(self):
        from django.db.models import Sum
        return self.entries.aggregate(s=Sum("hours_hh"))["s"] or 0

    @property
    def actual_hm(self):
        from django.db.models import Sum
        return self.entries.aggregate(s=Sum("hours_hm"))["s"] or 0


class ProductionEntry(models.Model):
    of_operation = models.ForeignKey("OFOperation", on_delete=models.CASCADE, related_name="entries")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="production_entries")
    hours_hh = models.DecimalField(max_digits=8, decimal_places=2)
    hours_hm = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    entry_date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        indexes = [models.Index(fields=["of_operation", "entry_date"])]


class ProductionObservation(models.Model):
    # SQ-COST-5: tolerância/semáforo de desvio de horas. Default ±5% nesta sprint —
    # não configurável por tenant (MVP). Puramente classificatório/apresentação: NÃO
    # altera delta_horas_pct (SQ-COST-3, calculado em services._close_out_observations).
    TOLERANCIA_HORAS_PCT = Decimal("5.00")

    STATUS_SEM_BASE = "sem_base"
    STATUS_DENTRO = "dentro"
    STATUS_ACIMA = "acima"
    STATUS_ABAIXO = "abaixo"

    operacao = models.CharField(max_length=100, db_index=True)
    ordem = models.ForeignKey("OrdemFabricacao", on_delete=models.PROTECT, related_name="observations")
    of_operation = models.ForeignKey("OFOperation", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="observations")
    estimated_custo = models.DecimalField(max_digits=14, decimal_places=2)
    actual_hh = models.DecimalField(max_digits=8, decimal_places=2)
    observed_rate = models.DecimalField(max_digits=12, decimal_places=2)
    # SQ-COST-3: decomposição horas orçadas (ProcessParameter) vs horas reais (apontamento),
    # aditivo — não afeta observed_rate/ActualRate (Welford), ver services._close_out_observations.
    estimated_hh = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    delta_horas_pct = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="(actual_hh − estimated_hh) / estimated_hh × 100. Null quando estimated_hh=0 "
                   "(operação de valor fixo, sem horas estimadas) — evita divisão por zero.",
    )
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [models.Index(fields=["operacao", "observed_at"])]

    @property
    def hours_variance_status(self):
        """SQ-COST-5: classifica delta_horas_pct contra a tolerância (±5.00%, MVP fixo
        nesta sprint). Somente leitura/apresentação — não recalcula nem persiste nada."""
        if self.delta_horas_pct is None:
            return self.STATUS_SEM_BASE
        if abs(self.delta_horas_pct) <= self.TOLERANCIA_HORAS_PCT:
            return self.STATUS_DENTRO
        if self.delta_horas_pct > self.TOLERANCIA_HORAS_PCT:
            return self.STATUS_ACIMA
        return self.STATUS_ABAIXO


class ActualRate(models.Model):
    operacao = models.CharField(max_length=100, unique=True)
    sample_count = models.PositiveIntegerField(default=0)
    mean_rate = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    m2 = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.operacao} N={self.sample_count} R$/h={self.mean_rate} conf={self.confidence}"


class InspectionPlan(models.Model):
    STATUS_OPEN = "open"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Aberto"),
        (STATUS_COMPLETED, "Concluído"),
    ]

    ordem = models.OneToOneField(
        "OrdemFabricacao", on_delete=models.CASCADE, related_name="inspection_plan")
    source_snapshot_hash = models.CharField(max_length=64, db_index=True)
    source_operations_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="inspection_plans_generated")
    generated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"ITP {self.ordem.number}"

    @property
    def accepted_count(self):
        return self.items.filter(status=InspectionItem.STATUS_ACCEPTED).count()


class InspectionItem(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_ACCEPTED, "Aceito"),
    ]

    plan = models.ForeignKey("InspectionPlan", on_delete=models.CASCADE, related_name="items")
    of_operation = models.ForeignKey(
        "OFOperation", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="inspection_items")
    sequence = models.PositiveSmallIntegerField(default=0)
    codigo_item = models.CharField(max_length=30)
    item_descricao = models.CharField(max_length=255)
    codigo_op = models.CharField(max_length=40)
    descricao = models.CharField(max_length=255)
    metodo = models.CharField(max_length=20, blank=True)
    inspection_type = models.CharField(max_length=30, default="processo")
    criterio = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="inspection_items_accepted")
    accepted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "of_operation"],
                condition=models.Q(of_operation__isnull=False),
                name="uniq_itp_item_per_operation",
            ),
            models.CheckConstraint(
                name="ck_itp_item_acceptance_consistent",
                condition=(
                    models.Q(status="pending", accepted_by__isnull=True, accepted_at__isnull=True)
                    | models.Q(status="accepted", accepted_by__isnull=False, accepted_at__isnull=False)
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["plan", "status", "sequence"]),
            models.Index(fields=["of_operation"]),
        ]

    def __str__(self):
        return f"{self.plan.ordem.number} · {self.codigo_op}"

    @property
    def is_accepted(self):
        return self.status == self.STATUS_ACCEPTED
