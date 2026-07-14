"""
Biblioteca de templates composicionais TEMA (TENANT schema).

Insight @WellToMcAt: template paramétrico por PARTE TEMA — cabeçote frontal (A/B/C/D/N),
casco (E/F/G/H/J/K/X), cabeçote traseiro (L/M/N/P/S/T/U/W) + sub-componentes do feixe.
Combina blocos pra "gerar" o trocador. Cotação parcial (só feixe) cai natural.

Compatibilidade entre letras = configurável (block/warn/free em TenantConfig — RESOLVIDO).
Custeio: o FEIXE já é computado pelo pricing_engine; casco/cabeçote (custeio paramétrico)
é a próxima milestone (operações + gabarito BEU já extraídos em seeds/beu_ground_truth.json).
"""
from django.db import models


class ComponentTemplate(models.Model):
    PART = [
        ("front_head", "Cabeçote Frontal"), ("shell", "Casco"),
        ("rear_head", "Cabeçote Traseiro"), ("tube_bundle", "Feixe Tubular"),
        ("tubesheet", "Espelho"), ("baffle", "Chicana"), ("tie_rod", "Tirante"),
        ("nozzle", "Bocal"), ("flange", "Flange"),
    ]
    tema_part = models.CharField(max_length=20, choices=PART, db_index=True)
    tema_letter = models.CharField(max_length=1, blank=True)   # A,B,E,F,S,U... (vazio p/ sub-componentes)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    standard_ref = models.CharField(max_length=120, blank=True)  # seção TEMA
    parameter_schema = models.JSONField(default=dict, blank=True)   # campos variáveis
    default_operations = models.JSONField(default=list, blank=True)  # roteiro padrão
    default_ndt = models.JSONField(default=list, blank=True)         # ensaios padrão
    is_global = models.BooleanField(default=True)   # global (catálogo) vs customizado do tenant
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tema_part", "tema_letter", "name"]
        constraints = [models.UniqueConstraint(
            fields=["tema_part", "tema_letter", "name"], name="uniq_tema_template")]

    def __str__(self):
        letra = f" {self.tema_letter}" if self.tema_letter else ""
        return f"{self.get_tema_part_display()}{letra} — {self.name}"


# Combinações TEMA válidas (front × rear) por tipo de construção.
# Regra de domínio simplificada: cabeçote traseiro flutuante (S/T/W/P) exige espelho
# flutuante; U = feixe em U (um espelho). Fonte: TEMA Fig. N-1.2.
VALID_REAR_FOR_FRONT = {
    # front: rears compatíveis (None = qualquer)
    "A": None, "B": None, "C": None, "N": ["N"], "D": None,
}
FLOATING_REARS = {"P", "S", "T", "W"}
U_TUBE_REARS = {"U"}


class ComponentOperation(models.Model):
    """Roteiro de fabricação SUGERIDO de um ComponentTemplate: QUAIS operações e qual driver
    físico usar. NÃO calcula horas aqui — isso é driver × ProcessParameter.objects.vigente(...)
    (outra task). `operacao` casa com engineering_params.ProcessParameter.operacao/Rate.operacao."""

    METODO = [("radial", "Radial"), ("cnc", "CNC"), ("manual", "Manual")]
    DRIVER = [
        ("diametro_bocal", "Ø bocal"), ("n_furos", "Nº furos"), ("n_tubos", "Nº tubos"),
        ("comprimento", "Comprimento"), ("diametro_casco", "Ø casco"),
        ("area_solda", "Área de solda"), ("massa", "Massa"), ("volume", "Volume"),
        ("fixo", "Fixo"),
    ]

    template = models.ForeignKey(
        "ComponentTemplate", on_delete=models.CASCADE, related_name="component_operations")
    codigo_op = models.CharField(max_length=40)
    descricao = models.CharField(max_length=255)
    operacao = models.CharField(max_length=100)
    metodo = models.CharField(max_length=20, choices=METODO, blank=True)
    driver = models.CharField(max_length=20, choices=DRIVER)
    setup_fixo = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    aplicavel_default = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "codigo_op"]

    def __str__(self):
        return f"{self.template} · {self.codigo_op} — {self.descricao}"


def check_compatibility(front: str, shell: str, rear: str) -> list[str]:
    """Retorna lista de avisos (vazia = combinação ok). Não bloqueia aqui (o caller decide
    block/warn/free conforme TenantConfig)."""
    avisos = []
    front, shell, rear = (front or "").upper(), (shell or "").upper(), (rear or "").upper()
    if front == "N" and rear != "N":
        avisos.append("Cabeçote frontal 'N' (integral ao espelho) normalmente exige traseiro 'N'.")
    if rear in FLOATING_REARS:
        avisos.append(f"Cabeçote traseiro '{rear}' é flutuante — exige espelho flutuante + flange de fechamento.")
    if rear in U_TUBE_REARS:
        avisos.append("Cabeçote traseiro 'U' = feixe em U (um único espelho, sem espelho traseiro).")
    if shell == "K" and rear not in {"U", "T"}:
        avisos.append("Casco 'K' (kettle reboiler) geralmente combina com feixe U ou pull-through (T).")
    return avisos
