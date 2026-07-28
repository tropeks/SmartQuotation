"""
Importa uma resposta do formulário externo (form.qtec.me) como vigência do tenant.

Uso:
    python manage.py tenant_command importar_estrutura_custo --schema=engematex \
        --arquivo /caminho/20260728-143000-engematex.json [--vigencia 2026-08-01]

Sem --vigencia, vale a partir de hoje. A vigência anterior é fechada na véspera —
nada é sobrescrito, porque cotação feita sob a régua antiga tem de continuar
reproduzindo aquela régua.
"""
import json
from datetime import date, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.cost_structure.services import (abrir_vigencia, da_resposta_do_formulario,
                                          diagnosticar)


class Command(BaseCommand):
    help = "Importa a resposta do formulário de estrutura de custo como nova vigência."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", required=True, help="JSON exportado do formulário")
        parser.add_argument("--vigencia", default=None, help="AAAA-MM-DD (default: hoje)")
        parser.add_argument("--simular", action="store_true",
                            help="Só mostra a conta, não grava")

    def handle(self, *args, **opts):
        caminho = Path(opts["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise CommandError(f"JSON inválido: {e}") from e

        vigencia = date.today()
        if opts["vigencia"]:
            try:
                vigencia = datetime.strptime(opts["vigencia"], "%Y-%m-%d").date()
            except ValueError as e:
                raise CommandError("--vigencia precisa ser AAAA-MM-DD") from e

        estrutura = da_resposta_do_formulario(dados, valid_from=vigencia)

        self.stdout.write(f"Empresa ............ {estrutura.empresa or '—'}")
        self.stdout.write(f"Mês de referência .. {estrutura.mes_referencia or '—'}")
        self.stdout.write(f"Custo da fábrica ... R$ {estrutura.custo_mensal:,.2f}/mês")
        self.stdout.write(f"Horas vendáveis .... {estrutura.horas_mes:,.0f} h/mês")
        custo_hora = estrutura.custo_hora
        self.stdout.write(self.style.SUCCESS(
            f"CUSTO REAL DA HORA . R$ {custo_hora}" if custo_hora
            else "CUSTO REAL DA HORA . — (capacidade não informada)"))

        d = diagnosticar(estrutura)
        estilo = self.style.ERROR if d["nivel"] == "prejuizo" else (
            self.style.WARNING if d["nivel"] in ("limite", "sem_rate", "sem_dados")
            else self.style.SUCCESS)
        self.stdout.write(estilo(f"\n{d['titulo']}: {d['texto']}"))
        if "delta" in d:
            self.stdout.write(f"  diferença por hora: R$ {d['delta']:.2f} ({d['pct']}%)")

        if opts["simular"]:
            self.stdout.write("\n(simulação — nada foi gravado)")
            return

        abrir_vigencia(estrutura)
        self.stdout.write(self.style.SUCCESS(
            f"\nVigência aberta em {estrutura.valid_from:%d/%m/%Y}. "
            f"A anterior, se existia, foi encerrada na véspera."))
