"""
Semeia a matriz papel×capability (DEFAULT_MATRIX) — tenant-aware e idempotente.

Uso:
    python manage.py seed_access_matrix                 # todos os tenants ativos
    python manage.py seed_access_matrix --schema engematex   # um tenant

Padrão schema_context (apps/integrations/sap_b1/tasks.py): itera os tenants ativos
e roda o seed dentro do contexto de schema de cada um. Idempotente (get_or_create):
não sobrescreve customizações já feitas por admins — só preenche lacunas.
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from apps.access.matrix import seed_access_matrix


class Command(BaseCommand):
    help = "Semeia RolePermission (DEFAULT_MATRIX) por tenant, idempotente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default=None,
            help="Limita a um schema de tenant específico (default: todos os ativos).",
        )

    def handle(self, *args, **opts):
        tenant_model = get_tenant_model()
        public = get_public_schema_name()
        qs = tenant_model.objects.exclude(schema_name=public).order_by("schema_name")
        if opts.get("schema"):
            qs = qs.filter(schema_name=opts["schema"])
        elif hasattr(tenant_model, "is_active"):
            # Sem --schema: só tenants ativos (com --schema, o operador é explícito).
            qs = qs.filter(is_active=True)

        tenants = list(qs)
        if not tenants:
            self.stdout.write(self.style.WARNING("Nenhum tenant encontrado."))
            return

        total = 0
        for tenant in tenants:
            with schema_context(tenant.schema_name):
                result = seed_access_matrix()
            total += result["created"]
            self.stdout.write(
                f"{tenant.schema_name}: +{result['created']} criadas, "
                f"{result['existing']} já existentes."
            )
        self.stdout.write(self.style.SUCCESS(f"OK: {total} permissões criadas."))
