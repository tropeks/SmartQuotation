"""
Concilia horas pagas × horas orçadas e mostra o fator de correção da mão de obra.

Uso:
    python manage.py tenant_command conciliar_horas --schema=engematex \\
        --horas-pagas 2000 --desde 2026-04-01 --ate 2026-06-30 [--aplicar]

Sem `--aplicar`, só mostra. Aplicar muda `fator_correcao_mo`, que **reprecifica todas
as cotações do tenant** — por isso é opt-in explícito, nunca efeito colateral.
"""
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.cost_discovery.reconciliacao import (horas_estimadas_de, limites_conhecidos,
                                               reconciliar)


class Command(BaseCommand):
    help = "Calibra a MO contra as horas da folha, em vez do preço histórico."

    def add_arguments(self, parser):
        parser.add_argument("--horas-pagas", required=True, type=float,
                            help="Total de horas pagas à produção no período")
        parser.add_argument("--desde", required=True, help="AAAA-MM-DD")
        parser.add_argument("--ate", required=True, help="AAAA-MM-DD")
        parser.add_argument("--aplicar", action="store_true",
                            help="Grava o fator (reprecifica TODAS as cotações)")

    def _data(self, texto, rotulo):
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError as e:
            raise CommandError(f"--{rotulo} precisa ser AAAA-MM-DD") from e

    def handle(self, *args, **opts):
        from apps.quotations.models import Quotation

        desde = self._data(opts["desde"], "desde")
        ate = self._data(opts["ate"], "ate")
        if ate < desde:
            raise CommandError("O período termina antes de começar.")

        cotacoes = Quotation.objects.filter(created_at__date__gte=desde,
                                            created_at__date__lte=ate)
        estimadas = horas_estimadas_de(cotacoes)
        r = reconciliar(opts["horas_pagas"], estimadas,
                        ofs=list(cotacoes.values_list("number", flat=True)))

        self.stdout.write(f"Período ............ {desde:%d/%m/%Y} a {ate:%d/%m/%Y}")
        self.stdout.write(f"Cotações no período  {len(r.ofs)}")
        self.stdout.write(f"Horas ORÇADAS ...... {r.horas_estimadas:,.2f} h")
        self.stdout.write(f"Horas PAGAS ........ {r.horas_pagas:,.2f} h")

        if not r.tem_resultado:
            self.stdout.write(self.style.WARNING(f"\n{r.titulo}: {r.texto}"))
            return

        estilo = self.style.SUCCESS if r.nivel == "calibrado" else self.style.WARNING
        self.stdout.write(estilo(
            f"\nFATOR DE CORREÇÃO DA MO: {r.fator} × ({r.desvio_pct:+}%)"))
        self.stdout.write(f"{r.titulo}: {r.texto}")

        self.stdout.write("\nO que este número NÃO diz:")
        for limite in limites_conhecidos():
            self.stdout.write(f"  · {limite}")

        if not opts["aplicar"]:
            self.stdout.write(self.style.WARNING(
                "\n(nada foi gravado — rode com --aplicar para adotar este fator)"))
            return

        from apps.engineering_params.models import TenantParamConfig

        cfg = TenantParamConfig.get_solo()
        anterior = cfg.fator_correcao_mo
        cfg.fator_correcao_mo = Decimal(str(r.fator))
        cfg.save(update_fields=["fator_correcao_mo"])
        self.stdout.write(self.style.SUCCESS(
            f"\nfator_correcao_mo: {anterior} → {cfg.fator_correcao_mo}. "
            f"As próximas cotações usam a nova régua; as já calculadas só mudam se "
            f"forem recomputadas."))
