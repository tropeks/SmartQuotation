"""
Catálogo de materiais (TENANT schema).
- Material.densidade = dado de NORMA (constante física).
- MaterialPrice = R$/kgf por (material × forma), TENANT-editável, CIFRADO, versionado.
  Base de custo: peso BRUTO (Opção A — cobra perdas). Ver pricing_engine.
"""
from django.db import models
from django.utils import timezone
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


class MaterialPriceManager(models.Manager):
    """Resolve "qual preço vale nesta data" — em UM lugar só.

    A mesma pergunta estava respondida em três (`materials/views.py`,
    `quotations/adapter.py`, `cost_discovery/services.py`) e as respostas divergiam: as
    duas do custeio iteravam sem `order_by` e deixavam o último registro do queryset
    vencer, então com duas vigências válidas no mesmo dia o preço que entrava no
    orçamento dependia da ordem em que o banco devolvesse as linhas.

    Regra (mesma de `RateManager.vigente`): `valid_from <= data` e (`valid_until` nulo
    ou `>= data`); em sobreposição vence o `valid_from` mais recente, desempatando pelo
    cadastro mais novo.
    """

    def _vigentes_qs(self, on_date=None):
        on_date = on_date or timezone.now().date()
        return (
            self.get_queryset()
            .filter(valid_from__lte=on_date)
            .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=on_date))
        )

    def vigente(self, material, forma, on_date=None):
        """O preço vigente de (material, forma) numa data, ou None."""
        return (
            self._vigentes_qs(on_date)
            .filter(material=material, forma=forma)
            .order_by("-valid_from", "-created_at", "-id")
            .first()
        )

    def mapa_vigente(self, on_date=None):
        """{(sigla_maiúscula, forma_minúscula): Decimal} — um preço por par.

        É o formato que a cadeia de custos do motor consome. Ordena crescente e deixa o
        mais recente sobrescrever, então o último a entrar no dict é o vigente.
        """
        from decimal import Decimal, InvalidOperation

        mapa = {}
        for preco in (self._vigentes_qs(on_date)
                      .select_related("material")
                      .order_by("valid_from", "created_at", "id")):
            try:
                valor = Decimal(str(preco.preco_brl_kg))
            except (TypeError, ValueError, InvalidOperation):
                continue
            mapa[(preco.material.sigla.upper(), preco.forma.lower())] = valor
        return mapa


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

    objects = MaterialPriceManager()

    class Meta:
        indexes = [models.Index(fields=["material", "forma", "valid_from"])]

    def __str__(self):
        return f"{self.material.sigla} {self.forma}"


class LigaMetalurgica(models.Model):
    """Classe metalúrgica EDITÁVEL pelo tenant (#2 Wellington): permite cadastrar ligas novas
    sem deploy. Carrega a tensão admissível S (curva por temperatura), os fatores de custo
    (MO/densidade/preço) e a PROCEDÊNCIA normativa (rastreabilidade de certificação ASME).
    Os dicts hardcoded em pricing_engine.asme / tema_templates.services continuam como FALLBACK
    quando a liga não está cadastrada (engine puro e gate não dependem do banco)."""
    codigo = models.CharField(max_length=30, db_index=True)        # CS, INOX, INCONEL, ou custom
    nome = models.CharField(max_length=100)                        # "Inconel 625"
    familia = models.CharField(max_length=60, blank=True)          # "Ni-Cr-Mo"
    spec = models.CharField(max_length=60, blank=True)             # "SB-443 N06625"
    # curva de tensão admissível S em MPa por °C: {"40": 217, "300": 205, ...}. Acima da maior
    # temperatura da curva → S indisponível (NÃO extrapola; idem pricing_engine.asme).
    s_curva = models.JSONField(default=dict, blank=True)
    liga_fator = models.DecimalField(max_digits=6, decimal_places=3, default=1)      # escala MO
    densidade_kg_mm3 = models.DecimalField(max_digits=12, decimal_places=10, default=0)  # 0 = usa CS
    preco_fator = models.DecimalField(max_digits=8, decimal_places=3, default=1)     # R$/kg vs CS
    temp_limite_c = models.IntegerField(default=370)               # aviso de fluência
    # procedência normativa (certificação ASME)
    norma = models.CharField(max_length=60, blank=True)            # "ASME BPVC II-D (M)"
    edicao = models.CharField(max_length=10, blank=True)           # "2025"
    tabela = models.CharField(max_length=10, blank=True)           # "1B"
    linha = models.CharField(max_length=10, blank=True)            # "22"
    is_active = models.BooleanField(default=True)
    ordem = models.IntegerField(default=100)                       # ordem no dropdown da UI

    class Meta:
        ordering = ["ordem", "codigo"]
        constraints = [models.UniqueConstraint(fields=["codigo"], name="uniq_liga_codigo")]

    def __str__(self):
        return f"{self.codigo} — {self.nome}"

    def procedencia(self):
        """Citação curta da fonte normativa do S (None se não registrada)."""
        if not (self.norma and self.edicao):
            return None
        ln = f" L{self.linha}" if self.linha else ""
        return f"{self.norma} {self.edicao}, Tab {self.tabela}{ln}"

    def s_curva_num(self):
        """s_curva com chaves de temperatura como float (JSON guarda como string)."""
        out = {}
        for k, v in (self.s_curva or {}).items():
            try:
                out[float(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out


class MaterialStandard(models.Model):
    """Dicionário de normas ASTM por (família metalúrgica × componente TEMA) — PE Wellington.

    Fonte da verdade = pricing_engine/seeds/material_standards.json (carregado por
    seed_material_standards). TENANT-editável no admin (empresa pode ter norma própria).
    Dirige o DATABOOK DE SUPRIMENTOS: dado o modelo TEMA cotado, emite a norma ASTM exata
    exigida por componente no Pedido de Compra (+ condição normativa e requisitos de qualidade).
    """
    FAMILIA = [
        ("aco_carbono", "Aço Carbono"), ("inox_304L", "Inox 304L"),
        ("inox_316L", "Inox 316L"), ("geral", "Geral (independe de liga)"),
    ]
    COMPONENTE = [
        ("chapas_pressao", "Chapas de pressão"), ("tubos_troca", "Tubos de troca"),
        ("tubos_bocais", "Tubos de bocais"), ("forjados_flanges", "Forjados/Flanges"),
        ("barras_chicanas", "Barras/Chicanas"),
        ("estojos_prisioneiros", "Estojos/Prisioneiros"), ("porcas", "Porcas"),
        ("junta_cabecote", "Junta de cabeçote"),
    ]
    familia = models.CharField(max_length=20, choices=FAMILIA, db_index=True)
    componente = models.CharField(max_length=20, choices=COMPONENTE, db_index=True)
    norma_astm = models.CharField(max_length=120)                 # "ASTM A516 Gr. 70"
    condicao = models.CharField(max_length=255, blank=True)       # regra/alternativa (ex: normalizado se T<-29°C)
    certificacao = models.CharField(max_length=60, default="EN 10204 3.1")
    notas = models.CharField(max_length=255, blank=True)          # RCB-2.2, UG-20(f), Eddy Current...
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["familia", "componente"]
        constraints = [models.UniqueConstraint(
            fields=["familia", "componente"], name="uniq_material_standard")]

    def __str__(self):
        return f"{self.get_familia_display()} · {self.get_componente_display()} → {self.norma_astm}"
