"""Ordem 008 (rodada de conserto) — `tema_templates.services.tenant_cost_chain()` e
`.tenant_pricing_completo()` engoliam `except Exception: pass` sem SAVEPOINT e sem log.

Mesmo defeito já corrigido em `apps.quotations.adapter.build_cost_chain` na ordem 007: um
erro de banco DE VERDADE dentro de um `except Exception` sem savepoint deixa a transação
Postgres inteira ABORTADA — a PRÓXIMA query, mesmo fora do `try`, bate em "current
transaction is aborted" em vez de só cair no default. Réplica do mesmo padrão: cada bloco
abre seu próprio `transaction.atomic()` (savepoint) + `logger.warning` no fallback (sem log,
um erro real de banco era indistinguível de "tenant sem dados configurados").

Prova com erro de banco REAL (não mock em memória — só assim a transação Postgres fica
genuinamente abortada, mesmo padrão de `tests_ordem_007_revise_feixe_savepoint.py`).
"""
from unittest.mock import patch

from django.db import connection, transaction

from apps.quotations.models import Customer
from apps.quotations.tests import TenantMigrationTestCase


def _erro_de_banco_real(*args, **kwargs):
    """Um erro de banco DE VERDADE — só assim a transação Postgres fica genuinamente
    abortada, reproduzindo o sintoma."""
    with connection.cursor() as cur:
        cur.execute("SELECT 1/0")


class TenantCostChainSavepointTests(TenantMigrationTestCase):
    def test_erro_no_material_price_nao_aborta_a_transacao_externa(self):
        from apps.tema_templates.services import tenant_cost_chain

        with transaction.atomic():
            with patch("apps.materials.models.MaterialPrice.objects.select_related",
                       side_effect=_erro_de_banco_real):
                with self.assertLogs("apps.tema_templates.services", level="WARNING"):
                    chain = tenant_cost_chain()
            # a transação de fora continua utilizável: nenhuma "current transaction aborted"
            Customer.objects.create(company_name="Prova pós-erro (material_price)")

        self.assertEqual(chain.material_price, {})

    def test_erro_no_rate_nao_aborta_a_transacao_externa(self):
        from apps.tema_templates.services import tenant_cost_chain

        with transaction.atomic():
            with patch("apps.engineering_params.models.Rate.objects.filter",
                       side_effect=_erro_de_banco_real):
                with self.assertLogs("apps.tema_templates.services", level="WARNING"):
                    chain = tenant_cost_chain()
            Customer.objects.create(company_name="Prova pós-erro (rate)")

        self.assertEqual(chain.rate_hh, {})


class TenantPricingCompletoSavepointTests(TenantMigrationTestCase):
    def test_erro_no_tenantparamconfig_nao_aborta_a_transacao_externa(self):
        from apps.tema_templates.services import tenant_pricing_completo

        with transaction.atomic():
            with patch("apps.engineering_params.models.TenantParamConfig.get_solo",
                       side_effect=_erro_de_banco_real):
                with self.assertLogs("apps.tema_templates.services", level="WARNING"):
                    fator_preco, impostos_pct = tenant_pricing_completo()
            Customer.objects.create(company_name="Prova pós-erro (pricing)")

        self.assertEqual((fator_preco, impostos_pct), (1.25, 9.0))
