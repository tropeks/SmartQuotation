"""
Ordem 007 — `adapter.revise_feixe` roda `recompute()` DENTRO do mesmo `transaction.atomic()`
que persiste a revisão. `build_cost_chain` (chamado por `_recompute_feixe`) engole erro de
banco com `except Exception: pass` em volta de duas consultas (preço de material vigente;
Rate/ProcessParameter/TenantParamConfig) — de propósito, para cair nos defaults quando a
consulta falha. Um erro REAL de banco ali, porém, deixa a transação Postgres ABORTADA; a
PRÓXIMA query (criar o CalculationSnapshot, ou qualquer coisa depois) bateria em "current
transaction is aborted" — 500 em vez de continuar com os defaults, exatamente o sintoma já
documentado (e corrigido) para `revise_complete` em `RevisePermutadorForaDaTransacaoTests`
(tests.py).

`_recompute_feixe` COMPUTA (chama `quote_feixe`) e PERSISTE (grava QuotationItem/
ItemMaterial/ItemOperation) na MESMA função, para uma `Quotation` que só existe depois do
INSERT dentro da transação de `revise_feixe` — não dá pra "calcular fora, persistir dentro"
sem reescrever esse caminho histórico ("intocado" desde a ordem 004). O conserto aqui é
proteger as DUAS consultas engolidas de `build_cost_chain` com SAVEPOINT
(`transaction.atomic()` aninhado): se a consulta falhar, só o savepoint desfaz — a
transação de fora continua utilizável.
"""
from unittest.mock import patch

from django.db import connection

from apps.quotations.models import Customer, Quotation
from apps.quotations.services import create_feixe_quotation
from apps.quotations.tests import TenantMigrationTestCase


def _erro_de_banco_real(*args, **kwargs):
    """Um erro de banco DE VERDADE (não um mock em memória) — só assim a transação
    Postgres fica genuinamente abortada, reproduzindo o sintoma relatado."""
    with connection.cursor() as cur:
        cur.execute("SELECT 1/0")


class ReviseFeixeForaDaTransacaoTests(TenantMigrationTestCase):
    """TransactionTestCase (via TenantMigrationTestCase), não TenantTestCase — pelo MESMO
    motivo documentado em RevisePermutadorForaDaTransacaoTests: o TestCase comum já embrulha
    cada teste no próprio atomic(), o que mascara a diferença entre "dentro" e "fora" da
    transação do código de produção."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(company_name="ACME TX Feixe")

    def test_erro_de_banco_engolido_no_material_price_nao_impede_a_revisao(self):
        from apps.quotations.adapter import revise_feixe

        orig = create_feixe_quotation(self.customer, "Feixe TX material price")

        with patch("apps.materials.models.MaterialPrice.objects.mapa_vigente",
                   side_effect=_erro_de_banco_real):
            revisada = revise_feixe(orig, created_by=None)

        self.assertEqual(revisada.status, "draft")
        self.assertEqual(revisada.number, orig.number)
        self.assertEqual(revisada.revision, 1)
        self.assertGreater(revisada.custo_total, 0)

    def test_erro_de_banco_engolido_no_rate_nao_impede_a_revisao(self):
        from apps.quotations.adapter import revise_feixe

        orig = create_feixe_quotation(self.customer, "Feixe TX rate")

        with patch("apps.engineering_params.models.Rate.objects.filter",
                   side_effect=_erro_de_banco_real):
            revisada = revise_feixe(orig, created_by=None)

        self.assertEqual(revisada.status, "draft")
        self.assertEqual(revisada.number, orig.number)
        self.assertEqual(revisada.revision, 1)
        self.assertGreater(revisada.custo_total, 0)
