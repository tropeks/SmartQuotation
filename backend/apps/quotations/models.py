"""
Cotação + Estrutura Analítica (EAP/WBS) persistida (TENANT schema).

Espinha dorsal (alinhamento @WellToMcAt):
  Quotation (N0) -> QuotationItem (N1) -> {ItemMaterial (N2), ItemOperation (N2)}
Os códigos (item/mp/op) viram BOM + roteiro de fabricação no H2 (zero retrabalho).

Persistência = SNAPSHOT do que o pricing_engine computou (deep-copy, não referência viva).
Dinheiro em Decimal (centavos). Peso BRUTO = base de custo (Opção A — cobra perdas);
peso LÍQUIDO informativo (refugo = bruto - líquido).
"""
from decimal import Decimal
from django.conf import settings
from django.db import models


class Customer(models.Model):
    company_name = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.company_name


class Quotation(models.Model):
    STATUS = [("draft", "Rascunho"), ("in_review", "Em Revisão"),
              ("approved", "Aprovada"), ("sent", "Enviada"),
              ("won", "Ganha"), ("lost", "Perdida")]
    SCOPE = [("tube_bundle", "Feixe Tubular"), ("complete", "Equipamento Completo"),
             ("parts", "Peças de Reposição")]
    # Proveniência do preço (SQ-COST-1 spec §5). NÃO é um campo de formulário livre:
    # `validado_custo` só passa a ser atingível quando existir CostStructure/preço mínimo
    # (SQ-COST-4/5) e a derivação automática correspondente. Até lá, toda cotação —
    # nova ou legada — é `referencial` (default explícito, nunca o oposto).
    PRICING_BASIS = [("referencial", "Referencial"),
                      ("validado_custo", "Validado por custo")]

    number = models.CharField(max_length=50, unique=True)
    revision = models.PositiveSmallIntegerField(default=0)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="quotations")
    title = models.CharField(max_length=500)
    scope = models.CharField(max_length=20, choices=SCOPE, default="tube_bundle")
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    # editable=False: fora de qualquer ModelForm (data sheet/edit) por construção — evita que
    # o orçamentista marque "validado por custo" manualmente. Só admin/leitura e código de
    # derivação automática (futuro) devem tocar este campo.
    pricing_basis = models.CharField(max_length=20, choices=PRICING_BASIS,
                                      default="referencial", editable=False)

    # --- inputs do data sheet do feixe (params que o orçamentista preenche) ---
    inputs = models.JSONField(default=dict, blank=True)   # serializa FeixeInputs

    # --- avisos de validação (metalurgia/térmica/geometria) empilhados no recompute ---
    avisos = models.JSONField(default=list, blank=True)    # [{nivel, codigo, mensagem}]

    # --- formação de preço (config do tenant; default reproduz gabarito) ---
    fator_preco = models.DecimalField(max_digits=8, decimal_places=5, default=Decimal("1.01377"))
    impostos_pct = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("23.303"))

    # --- totais computados (snapshot do roll-up) ---
    custo_material = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_mo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    preco_sem_impostos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    preco_com_impostos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    peso_bruto_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    peso_liquido_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="quotations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    computed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} — {self.title}"

    @property
    def perda_kg(self):
        return self.peso_bruto_kg - self.peso_liquido_kg


class CalculationSnapshot(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="snapshots")
    snapshot_hash = models.CharField(max_length=64, db_index=True)
    inputs = models.JSONField(default=dict, blank=True)
    outputs = models.JSONField(default=dict, blank=True)
    engine_version = models.CharField(max_length=50)
    standard_refs = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class QuotationItem(models.Model):
    """Nível 1 — componente/grupo da EAP (tubos, espelhos, chicanas, montagem...)."""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="itens")
    codigo_item = models.CharField(max_length=30)
    descricao = models.CharField(max_length=255)
    custo_material = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_mo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "codigo_item"]

    @property
    def custo_total(self):
        return self.custo_material + self.custo_mo


class ItemMaterial(models.Model):
    """Nível 2 — matéria-prima de um item (peso bruto/líquido, custo)."""
    item = models.ForeignKey(QuotationItem, on_delete=models.CASCADE, related_name="materiais")
    codigo_mp = models.CharField(max_length=30)
    descricao = models.CharField(max_length=255)
    material = models.CharField(max_length=50)
    forma = models.CharField(max_length=20)
    peso_bruto_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    peso_liquido_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    preco_kgf = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    custo = models.DecimalField(max_digits=14, decimal_places=2, default=0)


class ItemOperation(models.Model):
    """Nível 2 — operação do roteiro de um item (custo).

    Override NÃO-DESTRUTIVO: `horas_*_sugerida` guarda a sugestão do motor ao lado do
    valor efetivo (`horas_*`); `origem` diz de onde veio o valor corrente
    (seed=motor feixe/completo | template=ComponentOperation | manual=digitado pelo
    orçamentista). Sobrescrever no drawer marca origem='manual' SEM apagar a sugestão,
    para o UI mostrar "sugerido X / você digitou Y" e permitir restaurar.
    """
    ORIGEM = [("seed", "Motor"), ("template", "Template"), ("manual", "Manual")]

    item = models.ForeignKey(QuotationItem, on_delete=models.CASCADE, related_name="operacoes")
    codigo_op = models.CharField(max_length=40)
    descricao = models.CharField(max_length=255)
    metodo = models.CharField(max_length=20, blank=True)
    custo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    horas_hh = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    horas_hm = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    taxa_hora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxa_hora_hm = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    custo_direto = models.BooleanField(default=True)
    aplicavel = models.BooleanField(default=True)
    origem = models.CharField(max_length=10, choices=ORIGEM, default="seed")
    horas_hh_sugerida = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    horas_hm_sugerida = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    def recalc_custo(self):
        if self.custo_direto:
            return self.custo

        self.custo = (self.horas_hh * self.taxa_hora) + (self.horas_hm * self.taxa_hora_hm)
        if self.pk:
            self.save(update_fields=["custo"])
        return self.custo


class QuotationPart(models.Model):
    """Composição por PARTES avulsas (scope='parts'): quais componentes TEMA entram na
    cotação — casco só, cabeçote só, feixe reto/U só, ou a combinação p/ montar o
    equipamento. Cada linha aponta um ComponentTemplate + a geometria/material DESTA
    instância. Alimenta o custeio (adapter.recompute ramo 'parts') e o Databook."""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="parts")
    template = models.ForeignKey("tema_templates.ComponentTemplate",
                                 on_delete=models.PROTECT, related_name="+")
    tema_letter = models.CharField(max_length=1, blank=True)          # A/B/E/F/U/S...
    material_sigla = models.CharField(max_length=50, blank=True)      # sigla do Material (ex SA-516 GR 70)
    params = models.JSONField(default=dict, blank=True)              # geometria da instância (Ø, comp, nº furos, massa...)
    incluso = models.BooleanField(default=True)                      # p/ ligar/desligar a peça na cotação
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.quotation.number} · {self.template} ({self.material_sigla or '—'})"
