"""
Seed das ligas metalúrgicas no schema do tenant a partir das constantes 2025 (fonte única:
pricing_engine.asme + tema_templates.services). Idempotente (update_or_create por código).
Uso: python manage.py tenant_command seed_ligas --schema=engematex
"""
from decimal import Decimal
from django.core.management.base import BaseCommand

from apps.materials.models import LigaMetalurgica
from pricing_engine.asme import (CLASSE_SPEC, TENSAO_ADMISSIVEL_MPA, S_PROCEDENCIA, TEMP_LIMITE)
from apps.tema_templates.services import LIGA_FATOR, CLASSE_DENSIDADE, PRECO_FATOR

# metadados de exibição por classe (código → nome, família, ordem no dropdown)
META = {
    "CS":      ("Aço Carbono (SA-516 GR 70)", "C-Mn", 10),
    "INOX":    ("Aço Inox 304 (SA-240)", "Cr-Ni austenítico", 20),
    "DUPLEX":  ("Duplex 2205 (S31803)", "Fe-Cr-Ni duplex", 30),
    "INCONEL": ("Inconel 625", "Ni-Cr-Mo", 40),
    "MONEL":   ("Monel 400", "Ni-Cu", 50),
}


class Command(BaseCommand):
    help = "Carrega as ligas metalúrgicas (curva S 2025 + fatores + procedência) no tenant."

    def handle(self, *args, **opts):
        criadas = atualizadas = 0
        for codigo, (nome, familia, ordem) in META.items():
            spec = CLASSE_SPEC.get(codigo, "")
            s_tab = TENSAO_ADMISSIVEL_MPA.get(spec, {})
            s_curva = {str(t): float(v) for t, v in s_tab.items()}
            proc = S_PROCEDENCIA.get(spec, {})
            dens = CLASSE_DENSIDADE.get(codigo, 0) or 0
            defaults = dict(
                nome=nome, familia=familia, spec=spec, s_curva=s_curva,
                liga_fator=Decimal(str(LIGA_FATOR.get(codigo, 1.0))),
                densidade_kg_mm3=Decimal(str(dens)),
                preco_fator=Decimal(str(PRECO_FATOR.get(codigo, 1.0))),
                temp_limite_c=int(TEMP_LIMITE.get(codigo, 370)),
                norma=proc.get("norma", ""), edicao=proc.get("edicao", ""),
                tabela=proc.get("tabela", ""), linha=proc.get("linha", "") or "",
                is_active=True, ordem=ordem,
            )
            _, created = LigaMetalurgica.objects.update_or_create(codigo=codigo, defaults=defaults)
            criadas += int(created)
            atualizadas += int(not created)
        self.stdout.write(self.style.SUCCESS(
            f"Ligas: {criadas} criadas, {atualizadas} atualizadas."))
