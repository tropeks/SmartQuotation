"""
Ordem 007 — `services.allocate_revision` (P3) e a tradução de `IntegrityError` numa
corrida de revisão concorrente em `RevisionConflictError` (mensagem de conflito ao
usuário, nunca um 500).

IMPORTANTE (achado do revisor): o teste de corrida abaixo (`test_integrityerror_na_
corrida_vira_revisionconflicterror`) é MOCADO — ele força uma corrida que AINDA colide
(duas linhas tentando a MESMA revisão) e prova só a TRADUÇÃO do IntegrityError daí
resultante em RevisionConflictError. Ele NÃO prova que a trava (`pg_advisory_xact_lock` +
`select_for_update`, dentro de `allocate_revision`) SERIALIZA corretamente duas
transações concorrentes usando conexões Postgres reais — essa prova, com duas threads e
duas conexões de verdade, está em `tests_ordem_007_allocator_concurrencia.py`.
"""
from unittest import mock
from django.db import transaction
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer, Quotation
from apps.quotations.services import create_feixe_quotation


class AllocateRevisionTests(TenantTestCase):
    """`services.allocate_revision`: max(revision)+1 travado por select_for_update, entre
    TODAS as revisões do mesmo `number` (P3)."""

    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME Alocador")

    def test_aloca_1_para_numero_so_com_a_revisao_0(self):
        from apps.quotations.services import allocate_revision
        q = create_feixe_quotation(self.customer, "Feixe")
        with transaction.atomic():
            self.assertEqual(allocate_revision(q), 1)

    def test_p3_revisar_a_partir_de_revisao_antiga_sai_com_max_mais_1(self):
        """P3: revisar a Rev.0 depois que a Rev.2 já existe tem de sair com Rev.3, não
        Rev.1 (que colidiria com a Rev.1 já existente)."""
        from apps.quotations.services import allocate_revision
        rev0 = create_feixe_quotation(self.customer, "Feixe")
        Quotation.objects.create(number=rev0.number, revision=1, customer=self.customer,
                                 title="Feixe", scope="tube_bundle")
        Quotation.objects.create(number=rev0.number, revision=2, customer=self.customer,
                                 title="Feixe", scope="tube_bundle")
        with transaction.atomic():
            self.assertEqual(allocate_revision(rev0), 3)

    def test_integrityerror_na_corrida_vira_revisionconflicterror(self):
        """IntegrityError na UniqueConstraint(number, revision) — corrida entre duas
        revisões concorrentes — vira RevisionConflictError (mensagem de conflito), NUNCA
        deixa o IntegrityError cru subir (o que a view devolveria como 500)."""
        from apps.quotations.adapter import revise_feixe
        from apps.quotations.services import RevisionConflictError

        orig = create_feixe_quotation(self.customer, "Feixe corrida")
        # Simula a corrida: outra revisão (mesmo number, revision=1) já commitada por um
        # request concorrente ENTRE a alocação e o INSERT desta chamada. `real_create` é a
        # criação REAL (não o mock) — usada nas DUAS chamadas de dentro do side_effect,
        # senão a segunda chamada recursaria no próprio mock (RecursionError).
        real_create = Quotation.objects.create
        chamada = {"n": 0}

        def _cria_concorrente_e_prossegue(**kwargs):
            chamada["n"] += 1
            if chamada["n"] == 1:
                # request concorrente: grava a MESMA (number, revision) antes desta
                real_create(number=orig.number, revision=1, customer=self.customer,
                           title="Concorrente", scope="tube_bundle")
            return real_create(**kwargs)

        with mock.patch(
            "apps.quotations.adapter.Quotation.objects.create",
            side_effect=_cria_concorrente_e_prossegue,
        ):
            with self.assertRaises(RevisionConflictError):
                revise_feixe(orig, created_by=None)
