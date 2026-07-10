"""
Proposta comercial (TENANT schema).

Requisito @WellToMcAt: o TEXTO segue um TEMPLATE CONFIGURÁVEL (boilerplate do tenant),
mas pode ser EDITADO e CUSTOMIZADO por cotação.

  ProposalTemplate  -> texto-modelo do tenant (com placeholders {{...}}), reutilizável
  Proposal          -> instância por cotação; textos renderizados do template e EDITÁVEIS

A tabela de itens (EAP) e o preço NÃO são texto livre: vêm da cotação (computados).
Geração: PDF (HTML design G -> chrome --print-to-pdf) + DOCX (python-docx). Hash SHA-256.
"""
import hashlib
from django.conf import settings
from django.db import models
from django.utils import timezone


class ProposalTemplate(models.Model):
    """Template configurável de proposta (boilerplate do tenant, com placeholders)."""
    name = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # textos-modelo (Django Template; placeholders disponíveis no contexto — ver services.build_context)
    intro_template = models.TextField(
        default="Prezados, apresentamos nossa proposta para fornecimento de {{ titulo }}, "
                "conforme especificações técnicas a seguir.")
    scope_template = models.TextField(
        default="Escopo: {{ escopo }} — {{ n_tubos }} tubos {{ tubo_material }} "
                "{{ tubo_od }} x {{ tubo_parede }}, {{ tubo_comp_mm }} mm.")
    terms_template = models.TextField(
        default="Prazo de entrega: {{ delivery_weeks }} semanas. "
                "Validade da proposta: {{ validity_days }} dias. "
                "Condições de pagamento: {{ payment_terms }}.")
    # §4 Objeto da Proposta / §5 Exclusões do Fornecimento (modelos-default do tenant)
    object_template = models.TextField(
        default="Fornecimento de {{ titulo }} para {{ cliente }}, conforme especificações "
                "técnicas, memorial de cálculo e composição de preço a seguir.")
    exclusions_template = models.TextField(
        default="Não estão incluídos no fornecimento: frete e transporte, montagem em campo, "
                "obras civis, isolamento térmico, pintura externa e testes não destrutivos "
                "além dos especificados — salvo indicação expressa em contrário.")
    closing_template = models.TextField(
        default="Permanecemos à disposição para esclarecimentos.\nAtenciosamente,\n{{ empresa }}.")

    # defaults comerciais
    validity_days = models.PositiveIntegerField(default=30)
    delivery_weeks = models.PositiveIntegerField(default=8)
    payment_terms = models.CharField(max_length=255, default="30 dias da entrega")

    company_name = models.CharField(max_length=255, default="ENGEMATEX")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}{' (padrão)' if self.is_default else ''}"

    @classmethod
    def get_default(cls):
        return cls.objects.filter(is_active=True, is_default=True).first() or cls.objects.first()


class Proposal(models.Model):
    STATUS = [("draft", "Rascunho"), ("ready", "Pronta"), ("sent", "Enviada"), ("superseded", "Substituída")]

    quotation = models.ForeignKey("quotations.Quotation", on_delete=models.CASCADE, related_name="proposals")
    template = models.ForeignKey(ProposalTemplate, null=True, on_delete=models.SET_NULL)
    number = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")

    # textos EDITÁVEIS por caso (inicializados do template, depois customizáveis)
    intro_text = models.TextField(blank=True)
    scope_text = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    # §4 Objeto da Proposta / §5 Exclusões do Fornecimento (snapshot do template, editáveis)
    object_text = models.TextField(blank=True)
    exclusions_text = models.TextField(blank=True)
    closing_text = models.TextField(blank=True)

    # arquivos gerados (caminho relativo em MEDIA) + integridade
    docx_path = models.CharField(max_length=500, blank=True)
    pdf_path = models.CharField(max_length=500, blank=True)
    docx_sha256 = models.CharField(max_length=64, blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @staticmethod
    def sha256(path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


class ProposalVersion(models.Model):
    proposal = models.ForeignKey("proposals.Proposal", on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    number = models.CharField(max_length=100)
    pdf_path = models.CharField(max_length=500)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_proposal_versions",
    )
    emailed_at = models.DateTimeField(null=True, blank=True)
    emailed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emailed_proposal_versions",
    )
    email_to = models.EmailField(blank=True)

    class Meta:
        ordering = ["-version_number", "-generated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["proposal", "version_number"], name="uniq_proposal_version_number"),
        ]

    def __str__(self):
        return f"{self.number} v{self.version_number}"
