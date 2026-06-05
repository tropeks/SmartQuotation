"""
Cadeia de custos — wizard A1-c (TENANT schema).

Requisito reforçado (@WellToMcAt/@tropeks): ferramenta de 1ª classe pra o empresário
DEFINIR sua cadeia de custos. Dois métodos:
  - SEED top-down: entra os custos de cabeça (preços de material, fator de MO, markup).
  - BACK-SOLVE: calibra o fator de correção de MO contra um JOB REAL com preço conhecido,
    para que o motor reproduza a realidade da empresa.

O resultado popula MaterialPrice + TenantParamConfig (engineering_params), que o adapter
injeta no pricing_engine. Diferencial: PME de caldeiraria não tem cadeia de custo estruturada.
"""
from django.conf import settings
from django.db import models


class CostDiscoverySession(models.Model):
    METHOD = [("top_down", "Seed top-down"), ("back_solve", "Calibração (back-solve)")]

    method = models.CharField(max_length=20, choices=METHOD)
    # back-solve: job de referência (inputs do feixe) + preço final conhecido
    reference_inputs = models.JSONField(default=dict, blank=True)
    reference_known_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    solved_fator_mo = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    achieved_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    error_pct = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_method_display()} ({self.created_at:%d/%m/%Y})"
