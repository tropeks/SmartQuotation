"""Modelos de Ordem de Fabricação (H2.1)."""
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
    aplicavel = models.BooleanField(default=True)
    sequence = models.PositiveSmallIntegerField(default=0)
