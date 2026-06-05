"""
Seed dos parâmetros de engenharia ENGEMATEX a partir do pricing_engine.
Roda no schema do tenant atual.

- Rate: a partir de rates.engematex_seed() (rate_hh + rate_hm).
- ProcessParameter: a partir de process_params.CATALOG (operacao, metodo, valor, unidade, descricao).

Uso (no tenant):
    python manage.py tenant_command seed_engineering_params --schema=engematex
"""
import os
import sys
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.engineering_params.models import ProcessParameter, Rate


def _import_pricing_engine():
    """Importa rates e process_params do pricing_engine de forma robusta.

    O pacote vive no repo root (../../../../../../pricing_engine a partir daqui) e, no
    Docker, em /app/pricing_engine. Insere os candidatos no sys.path e importa.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    # here = .../backend/apps/engineering_params/management/commands
    # repo root (.../SmartQuotation) = 5 níveis acima; backend = 4 níveis acima.
    repo_root = os.path.abspath(os.path.join(here, *([os.pardir] * 5)))
    backend_root = os.path.abspath(os.path.join(here, *([os.pardir] * 4)))
    candidates = [repo_root, "/app", backend_root, os.getcwd()]
    for base in candidates:
        if base and os.path.isdir(os.path.join(base, "pricing_engine")):
            if base not in sys.path:
                sys.path.insert(0, base)
            break
    import pricing_engine.process_params as process_params  # noqa: E402
    import pricing_engine.rates as rates  # noqa: E402

    return rates, process_params


class Command(BaseCommand):
    help = "Carrega Rate (rate_hh/hm) e ProcessParameter (CATALOG) ENGEMATEX no schema do tenant."

    def handle(self, *args, **opts):
        rates, process_params = _import_pricing_engine()

        chain = rates.engematex_seed()
        rate_hh = chain.rate_hh
        rate_hm = chain.rate_hm

        # --- Rates: uma linha por operação que tenha rate_hh; rate_hm quando existir ---
        rate_criados = rate_atualizados = 0
        for operacao, hh in rate_hh.items():
            hm = rate_hm.get(operacao)
            _obj, created = Rate.objects.update_or_create(
                operacao=operacao,
                valid_from=Rate._meta.get_field("valid_from").default(),
                defaults=dict(
                    rate_hh=Decimal(str(hh)),
                    rate_hm=Decimal(str(hm)) if hm is not None else None,
                ),
            )
            rate_criados += created
            rate_atualizados += not created

        # rate_hm de operações que NÃO têm rate_hh (ex: USINAR_RASGOS, CHICANA_USINAR) ---
        for operacao, hm in rate_hm.items():
            if operacao in rate_hh:
                continue
            _obj, created = Rate.objects.update_or_create(
                operacao=operacao,
                valid_from=Rate._meta.get_field("valid_from").default(),
                defaults=dict(rate_hh=Decimal("0.00"), rate_hm=Decimal(str(hm))),
            )
            rate_criados += created
            rate_atualizados += not created

        # --- ProcessParameter: a partir do CATALOG (valor None = pendente, ex CNC) ---
        pp_criados = pp_atualizados = 0
        for (operacao, metodo), pp in process_params.CATALOG.items():
            valor = None if pp.valor is None else Decimal(str(pp.valor))
            _obj, created = ProcessParameter.objects.update_or_create(
                operacao=operacao,
                metodo=metodo,
                valid_from=ProcessParameter._meta.get_field("valid_from").default(),
                defaults=dict(
                    valor=valor,
                    unidade=pp.unidade,
                    descricao=pp.descricao or "",
                ),
            )
            pp_criados += created
            pp_atualizados += not created

        self.stdout.write(self.style.SUCCESS(
            f"Rate: {rate_criados} criados, {rate_atualizados} atualizados "
            f"(total {Rate.objects.count()}). "
            f"ProcessParameter: {pp_criados} criados, {pp_atualizados} atualizados "
            f"(total {ProcessParameter.objects.count()})."))
