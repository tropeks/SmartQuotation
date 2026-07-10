"""Cria o template de proposta padrão do tenant (boilerplate configurável)."""
from django.core.management.base import BaseCommand
from apps.proposals.models import ProposalTemplate


class Command(BaseCommand):
    help = "Cria/garante o template de proposta padrão do tenant."

    # §4 Objeto / §5 Exclusões — boilerplate default do tenant (feixe tubular / permutador)
    OBJECT_DEFAULT = (
        "Fornecimento de {{ titulo }} para {{ cliente }}, conforme especificações técnicas, "
        "memorial de cálculo e composição de preço a seguir.")
    EXCLUSIONS_DEFAULT = (
        "Não estão incluídos no fornecimento: frete e transporte, montagem em campo, obras "
        "civis, isolamento térmico, pintura externa e testes não destrutivos além dos "
        "especificados — salvo indicação expressa em contrário.")

    def handle(self, *args, **opts):
        tpl, created = ProposalTemplate.objects.get_or_create(
            name="Padrão ENGEMATEX", defaults={"is_default": True})
        if not tpl.is_default:
            ProposalTemplate.objects.update(is_default=False)
            tpl.is_default = True
        # garante os textos-modelo de §4 Objeto e §5 Exclusões (só se ainda vazios)
        if not tpl.object_template:
            tpl.object_template = self.OBJECT_DEFAULT
        if not tpl.exclusions_template:
            tpl.exclusions_template = self.EXCLUSIONS_DEFAULT
        tpl.save()
        self.stdout.write(self.style.SUCCESS(
            f"Template '{tpl.name}' {'criado' if created else 'já existia'} (padrão)."))
