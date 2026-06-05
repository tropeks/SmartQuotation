"""Cria o template de proposta padrão do tenant (boilerplate configurável)."""
from django.core.management.base import BaseCommand
from apps.proposals.models import ProposalTemplate


class Command(BaseCommand):
    help = "Cria/garante o template de proposta padrão do tenant."

    def handle(self, *args, **opts):
        tpl, created = ProposalTemplate.objects.get_or_create(
            name="Padrão ENGEMATEX", defaults={"is_default": True})
        if not tpl.is_default:
            ProposalTemplate.objects.update(is_default=False)
            tpl.is_default = True
            tpl.save()
        self.stdout.write(self.style.SUCCESS(
            f"Template '{tpl.name}' {'criado' if created else 'já existia'} (padrão)."))
