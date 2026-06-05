"""
Seed do catálogo de materiais a partir do seed do pricing_engine (423 materiais).
Roda no schema do tenant atual. Limpa densidades corrompidas na origem.
Uso (no tenant): python manage.py tenant_command seed_materials --schema=engematex
"""
import json
import os
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from apps.materials.models import Material

SEED = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..",
                    "pricing_engine", "seeds", "materials_pe.json")


class Command(BaseCommand):
    help = "Carrega os 423 materiais (densidade da norma) no schema do tenant."

    def handle(self, *args, **opts):
        with open(os.path.abspath(SEED), encoding="utf-8") as fp:
            raw = json.load(fp)
        criados = atualizados = pulados = 0
        for m in raw:
            sigla = (m.get("sigla") or "").strip()
            if not sigla:
                pulados += 1
                continue
            pe = m.get("pe_kg_mm3")
            try:
                dens = Decimal(str(pe)) if isinstance(pe, (int, float)) else None
            except (InvalidOperation, TypeError):
                dens = None
            obj, created = Material.objects.update_or_create(
                sigla=sigla,
                defaults=dict(
                    tipo=(m.get("tipo") or "").strip(),
                    densidade_kg_mm3=dens,
                    norma=(m.get("norma") or "").strip(),
                    forma_padrao=(m.get("prod") or "").strip(),
                ),
            )
            criados += created
            atualizados += not created
        self.stdout.write(self.style.SUCCESS(
            f"Materiais: {criados} criados, {atualizados} atualizados, {pulados} pulados. "
            f"Total no schema: {Material.objects.count()}"))
