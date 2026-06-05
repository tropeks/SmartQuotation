"""
Catálogo de materiais (TENANT schema).
- Material.densidade = dado de NORMA (constante física).
- MaterialPrice = R$/kgf por (material × forma), TENANT-editável, CIFRADO, versionado.
  Base de custo: peso BRUTO (Opção A — cobra perdas). Ver pricing_engine.
"""
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class Material(models.Model):
    sigla = models.CharField(max_length=50, db_index=True)          # SA-179, SA-516 GR 70
    tipo = models.CharField(max_length=100, blank=True)            # AÇO CARBONO, AÇO INOX SS-300
    densidade_kg_mm3 = models.DecimalField(max_digits=12, decimal_places=10, null=True, blank=True)
    norma = models.CharField(max_length=50, blank=True)
    forma_padrao = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sigla"]
        constraints = [models.UniqueConstraint(fields=["sigla"], name="uniq_material_sigla")]

    def __str__(self):
        return f"{self.sigla} ({self.tipo})"


class MaterialPrice(models.Model):
    FORMA = [("chapa", "Chapa"), ("tubo", "Tubo"), ("barra", "Barra"),
             ("forjado", "Forjado"), ("fundido", "Fundido")]
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="precos")
    forma = models.CharField(max_length=20, choices=FORMA)
    preco_brl_kg = EncryptedCharField(max_length=64)              # cifrado (preço sensível)
    fornecedor = models.CharField(max_length=255, blank=True)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["material", "forma", "valid_from"])]

    def __str__(self):
        return f"{self.material.sigla} {self.forma}"
