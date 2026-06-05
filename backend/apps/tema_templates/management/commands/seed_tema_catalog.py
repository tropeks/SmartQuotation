"""Seed do catálogo de partes TEMA (front/shell/rear heads + sub-componentes do feixe)."""
from django.core.management.base import BaseCommand
from apps.tema_templates.models import ComponentTemplate

FRONT = {"A": "Canal e tampa removível", "B": "Bonnet (tampo integral)",
         "C": "Canal integral ao espelho (feixe removível)", "N": "Canal integral ao casco e espelho",
         "D": "Fechamento especial alta pressão"}
SHELL = {"E": "Um passe no casco", "F": "Dois passes (chicana longitudinal)",
         "G": "Split flow", "H": "Double split flow", "J": "Divided flow",
         "K": "Kettle reboiler", "X": "Cross flow"}
REAR = {"L": "Igual A, espelho fixo", "M": "Igual B, espelho fixo", "N": "Igual N, espelho fixo",
        "P": "Cabeçote flutuante externo", "S": "Cabeçote flutuante com anel bipartido",
        "T": "Cabeçote flutuante pull-through", "U": "Feixe em U", "W": "Flutuante com gaxeta"}
SUB = [("tube_bundle", "Feixe Tubular", "RCB"), ("tubesheet", "Espelho", "RCB-7"),
       ("baffle", "Chicana", "RCB-4"), ("tie_rod", "Tirante", "RCB-4.71"),
       ("nozzle", "Bocal", "RCB-6"), ("flange", "Flange", "RGP")]


class Command(BaseCommand):
    help = "Seed do catálogo TEMA (partes + letras)."

    def handle(self, *args, **opts):
        n = 0
        for letra, nome in FRONT.items():
            _, c = ComponentTemplate.objects.get_or_create(
                tema_part="front_head", tema_letter=letra, name=nome,
                defaults={"standard_ref": "TEMA Fig. N-1.2"}); n += c
        for letra, nome in SHELL.items():
            _, c = ComponentTemplate.objects.get_or_create(
                tema_part="shell", tema_letter=letra, name=nome,
                defaults={"standard_ref": "TEMA Fig. N-1.2"}); n += c
        for letra, nome in REAR.items():
            _, c = ComponentTemplate.objects.get_or_create(
                tema_part="rear_head", tema_letter=letra, name=nome,
                defaults={"standard_ref": "TEMA Fig. N-1.2"}); n += c
        for part, nome, ref in SUB:
            _, c = ComponentTemplate.objects.get_or_create(
                tema_part=part, tema_letter="", name=nome, defaults={"standard_ref": ref}); n += c
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo TEMA: {n} novos. Total: {ComponentTemplate.objects.count()} "
            f"({len(FRONT)} front + {len(SHELL)} shell + {len(REAR)} rear + {len(SUB)} sub)."))
