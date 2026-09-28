"""
Ordem 007 — prova de concorrência REAL (duas conexões Postgres, não mock) do alocador
de revisão. `AllocateRevisionTests.test_integrityerror_na_corrida_vira_revisionconflicterror`
(tests_ordem_007_allocator.py) prova só a TRADUÇÃO IntegrityError -> RevisionConflictError
de uma corrida que AINDA colide; não prova que a trava em si serializa direito.

Achado do revisor: `select_for_update().filter(...).aggregate(Max(...))` perde o FOR UPDATE
em SILÊNCIO — Postgres não aceita `FOR UPDATE` numa consulta com agregação, e o Django
descarta a cláusula sem levantar erro. As duas conexões abaixo, sem a trava, calculam a
MESMA próxima revisão.
"""
import threading
import time

from django.db import IntegrityError, connections, transaction
from django.db.models import Max
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

from apps.quotations.models import Customer, Quotation
from apps.quotations.services import allocate_revision, create_feixe_quotation
from apps.quotations.tests import TenantMigrationTestCase


def _aggregate_sem_trava_real(orig: Quotation) -> int:
    """Reproduz o BUG relatado: `.select_for_update().aggregate(Max(...))` — o FOR UPDATE
    é descartado pelo Django (Postgres não aceita FOR UPDATE com agregação). Usado só para
    provar o sintoma antes do conserto; não é chamado pelo código de produção."""
    maior = (Quotation.objects.select_for_update()
             .filter(number=orig.number)
             .aggregate(Max("revision"))["revision__max"])
    base = maior if maior is not None else orig.revision
    return base + 1


class AllocateRevisionSqlEmiteForUpdateTests(TenantMigrationTestCase):
    """`allocate_revision` precisa emitir SQL com `FOR UPDATE` de verdade (não a versão
    agregada, que o Django descarta em silêncio)."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(company_name="ACME SQL FOR UPDATE")

    def test_sql_emitido_contem_for_update(self):
        q = create_feixe_quotation(self.customer, "Feixe SQL")
        with transaction.atomic():
            with CaptureQueriesContext(connections["default"]) as ctx:
                allocate_revision(q)
        sql_concatenado = " ".join(item["sql"].upper() for item in ctx.captured_queries)
        self.assertIn("FOR UPDATE", sql_concatenado)

    def test_versao_agregada_NAO_emite_for_update_documenta_o_bug_relatado(self):
        """Documenta o sintoma relatado pelo revisor: a forma com `.aggregate(Max(...))`
        NÃO emite `FOR UPDATE` (Django descarta a cláusula em silêncio quando a consulta
        agrega) — por isso `allocate_revision` NÃO pode usar essa forma."""
        q = create_feixe_quotation(self.customer, "Feixe SQL agregado")
        with transaction.atomic():
            with CaptureQueriesContext(connections["default"]) as ctx:
                _aggregate_sem_trava_real(q)
        sql_concatenado = " ".join(item["sql"].upper() for item in ctx.captured_queries)
        self.assertNotIn("FOR UPDATE", sql_concatenado)


class AllocateRevisionConcorrenciaRealTests(TenantMigrationTestCase):
    """Prova com DUAS CONEXÕES Postgres reais (threads + `TransactionTestCase`, dados
    realmente commitados): a segunda transação espera a primeira e sai com max+1, SEM
    IntegrityError — o mock de `tests_ordem_007_allocator.py` não prova isto (aquele
    prova a corrida que AINDA colide, traduzida em RevisionConflictError)."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(company_name="ACME Concorrência Real")
        self.orig = create_feixe_quotation(self.customer, "Feixe concorrência real")
        self.schema_name = self.tenant.schema_name

    def test_segunda_transacao_espera_e_sai_com_max_mais_1_sem_conflito(self):
        resultados = {}
        erros = {}
        t1_com_a_trava = threading.Event()
        t1_pode_commitar = threading.Event()
        t2_tentou_entrar = threading.Event()

        def _worker1():
            try:
                with schema_context(self.schema_name):
                    with transaction.atomic():
                        rev = allocate_revision(self.orig)
                        resultados["t1"] = rev
                        Quotation.objects.create(
                            number=self.orig.number, revision=rev, customer=self.customer,
                            title="T1", scope="tube_bundle")
                        t1_com_a_trava.set()
                        # segura a transação aberta até a t2 provar que ficou esperando
                        t1_pode_commitar.wait(timeout=5)
            except Exception as exc:      # pragma: no cover - só para não perder o erro
                erros["t1"] = exc
            finally:
                connections.close_all()

        def _worker2():
            try:
                t1_com_a_trava.wait(timeout=5)
                with schema_context(self.schema_name):
                    with transaction.atomic():
                        t2_tentou_entrar.set()
                        rev = allocate_revision(self.orig)   # deve BLOQUEAR até t1 commitar
                        resultados["t2"] = rev
                        Quotation.objects.create(
                            number=self.orig.number, revision=rev, customer=self.customer,
                            title="T2", scope="tube_bundle")
            except IntegrityError as exc:
                erros["t2"] = exc
            except Exception as exc:      # pragma: no cover
                erros["t2_outro"] = exc
            finally:
                connections.close_all()

        t1 = threading.Thread(target=_worker1)
        t2 = threading.Thread(target=_worker2)
        t1.start()
        self.assertTrue(t1_com_a_trava.wait(timeout=5), "t1 não conseguiu a trava a tempo")
        t2.start()
        self.assertTrue(t2_tentou_entrar.wait(timeout=5), "t2 não tentou entrar a tempo")
        # folga real: prova que a t2 ficou BLOQUEADA em allocate_revision (não terminou
        # instantaneamente) antes de liberar a t1 para commitar.
        time.sleep(0.4)
        self.assertNotIn("t2", resultados, "t2 não deveria ter terminado antes da t1 commitar")
        t1_pode_commitar.set()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(erros, {}, f"thread(s) com erro inesperado: {erros}")
        self.assertEqual(resultados.get("t1"), 1)
        self.assertEqual(resultados.get("t2"), 2)
        self.assertEqual(
            set(Quotation.objects.filter(number=self.orig.number)
                .values_list("revision", flat=True)),
            {0, 1, 2},
        )
