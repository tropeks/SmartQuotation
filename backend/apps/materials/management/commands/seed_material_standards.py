"""
Seed do dicionário de normas ASTM por (família × componente) — Databook de Suprimentos.
Fonte: pricing_engine/seeds/material_standards.json (PE Wellington). Roda no schema do tenant.
Uso: python manage.py tenant_command seed_material_standards --schema=engematex
"""
import json
import os
from django.core.management.base import BaseCommand
from apps.materials.models import MaterialStandard

SEED = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..",
                    "pricing_engine", "seeds", "material_standards.json")


class Command(BaseCommand):
    help = "Carrega o dicionário de normas ASTM por componente TEMA no schema do tenant."

    def handle(self, *args, **opts):
        with open(os.path.abspath(SEED), encoding="utf-8") as fp:
            raw = json.load(fp)
        cert_padrao = raw.get("requisitos_qualidade", {}).get("certificacao_padrao", "EN 10204 3.1")
        criados = atualizados = 0
        for s in raw.get("standards", []):
            _obj, created = MaterialStandard.objects.update_or_create(
                familia=s["familia"], componente=s["componente"],
                defaults=dict(
                    norma_astm=s["norma_astm"],
                    condicao=s.get("condicao", ""),
                    certificacao=s.get("certificacao", cert_padrao),
                    notas=s.get("notas", ""),
                    is_active=True,
                ),
            )
            criados += created
            atualizados += not created
        self.stdout.write(self.style.SUCCESS(
            f"Normas: {criados} criadas, {atualizados} atualizadas. "
            f"Total no schema: {MaterialStandard.objects.count()}"))
