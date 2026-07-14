"""
Seed do roteiro de fabricação SUGERIDO (ComponentOperation) por parte TEMA.
Fonte: pricing_engine/seeds/component_operations.json (PE). Roda no schema do tenant.
Uso: python manage.py tenant_command seed_component_operations --schema=engematex
"""
import json
import os
from django.core.management.base import BaseCommand
from apps.tema_templates.models import ComponentOperation, ComponentTemplate

SEED = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..",
                    "pricing_engine", "seeds", "component_operations.json")


class Command(BaseCommand):
    help = "Carrega o roteiro de fabricação sugerido (ComponentOperation) por parte TEMA no schema do tenant."

    def handle(self, *args, **opts):
        with open(os.path.abspath(SEED), encoding="utf-8") as fp:
            raw = json.load(fp)
        criados = atualizados = 0
        for roteiro in raw.get("roteiros", []):
            tema_part = roteiro["tema_part"]
            templates = ComponentTemplate.objects.filter(tema_part=tema_part)
            for template in templates:
                for op in roteiro.get("operacoes", []):
                    _obj, created = ComponentOperation.objects.update_or_create(
                        template=template, codigo_op=op["codigo_op"],
                        defaults=dict(
                            descricao=op["descricao"],
                            operacao=op["operacao"],
                            metodo=op.get("metodo", ""),
                            driver=op["driver"],
                            setup_fixo=op.get("setup_fixo", 0),
                            sort_order=op.get("sort_order", 0),
                        ),
                    )
                    criados += created
                    atualizados += not created
        self.stdout.write(self.style.SUCCESS(
            f"ComponentOperation: {criados} criadas, {atualizados} atualizadas. "
            f"Total no schema: {ComponentOperation.objects.count()}"))
