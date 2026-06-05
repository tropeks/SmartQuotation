"""
Cria um tenant (empresa cliente) com schema isolado.
Uso: python manage.py create_tenant --name "ENGEMATEX" --schema engematex --domain engematex.localhost
"""
from django.core.management.base import BaseCommand
from apps.tenants.models import Tenant, Domain


class Command(BaseCommand):
    help = "Cria um tenant com schema isolado (django-tenants)."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--schema", required=True)
        parser.add_argument("--domain", required=True)

    def handle(self, *args, **opts):
        schema = opts["schema"]
        if Tenant.objects.filter(schema_name=schema).exists():
            self.stdout.write(self.style.WARNING(f"Tenant '{schema}' já existe."))
            return
        tenant = Tenant.objects.create(name=opts["name"], schema_name=schema)  # auto_create_schema
        Domain.objects.create(domain=opts["domain"], tenant=tenant, is_primary=True)
        self.stdout.write(self.style.SUCCESS(
            f"Tenant '{tenant.name}' criado: schema={schema} domain={opts['domain']}"))
