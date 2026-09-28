"""
Ordem 007 — migração `quotations/0010_quotation_revision_keeps_number`.

`number` deixa de ser UNIQUE sozinho (vira db_index); ganha `UniqueConstraint(number,
revision)`; o RunPython reverso RECUSA desfazer se já existir `number` repetido (o par que
a nova constraint permite e a antiga proibia). Ver a migração para o porquê.
"""
from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor

from apps.quotations.models import Customer, Quotation
from apps.quotations.tests import TenantMigrationTestCase
from django_tenants.test.cases import TenantTestCase


class RevisionKeepsNumberMigrationTests(TenantMigrationTestCase):
    """Migração 0010 (ordem 007) — ida e volta, com e sem `number` repetido."""

    migrate_from = ("quotations", "0009_itemoperation_taxa_hora_hm_sugerida_and_more")
    migrate_to = ("quotations", "0010_quotation_revision_keeps_number")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_from])

        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        old_apps.get_model("quotations", "Customer").objects.create(
            company_name="Cliente legado 0010"
        )
        old_apps.get_model("quotations", "Quotation").objects.create(
            number="COT-LEGACY-0010-0001",
            customer=old_apps.get_model("quotations", "Customer").objects.get(
                company_name="Cliente legado 0010"),
            title="Cotacao legado 0010",
        )

        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        super().tearDown()

    def _quotation_e_cliente(self):
        Quotation = self.apps.get_model("quotations", "Quotation")
        Customer = self.apps.get_model("quotations", "Customer")
        return Quotation, Customer.objects.get(company_name="Cliente legado 0010")

    def test_ida_permite_duas_revisoes_com_o_mesmo_number(self):
        """A UniqueConstraint(number, revision) permite o PAR — é exatamente o que a
        feature de revisão-mantém-número precisa gravar."""
        Quotation, cust = self._quotation_e_cliente()
        Quotation.objects.create(number="COT-LEGACY-0010-0001", revision=1,
                                 customer=cust, title="Rev.1")
        self.assertEqual(
            Quotation.objects.filter(number="COT-LEGACY-0010-0001").count(), 2)

    def test_ida_rejeita_number_e_revision_repetidos(self):
        """O par (number, revision) continua único — duas linhas revision=0 do MESMO
        number NÃO podem coexistir."""
        Quotation, cust = self._quotation_e_cliente()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Quotation.objects.create(number="COT-LEGACY-0010-0001", revision=0,
                                         customer=cust, title="Duplicata revision 0")

    def test_volta_sem_repeticao_de_number_funciona(self):
        """Sem `number` repetido, o reverse (RunPython noop + drop da constraint +
        AlterField de volta a unique=True) completa normalmente."""
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_from])   # não deve levantar
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        self.assertEqual(
            old_apps.get_model("quotations", "Quotation")
            .objects.filter(number="COT-LEGACY-0010-0001").count(),
            1,
        )

    def test_volta_recusa_se_ja_existe_number_repetido(self):
        """A revisão-mantém-número já foi usada (existe uma Rev.1 com o MESMO number) —
        reverter recriaria a UNIQUE antiga em `number` sozinho, que essas duas linhas
        violam. O RunPython reverso recusa ANTES do Postgres estourar um erro de
        constraint cru."""
        Quotation, cust = self._quotation_e_cliente()
        Quotation.objects.create(number="COT-LEGACY-0010-0001", revision=1,
                                 customer=cust, title="Rev.1")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        with self.assertRaises(RuntimeError):
            executor.migrate([self.migrate_from])


class RefuseDowngradeGuardUnitTests(TenantTestCase):
    """Teste direto da função-guarda do reverse (padrão sugerido pela ordem quando um
    teste de migração completo é redundante): chama `_refuse_downgrade_if_duplicate_numbers`
    contra o app registry REAL (já na migração 0010, estado corrente do schema de teste)."""

    def _migration_module(self):
        import importlib
        return importlib.import_module(
            "apps.quotations.migrations.0010_quotation_revision_keeps_number"
        )

    def test_sem_number_repetido_nao_levanta(self):
        import django.apps as django_apps
        mod = self._migration_module()
        customer = Customer.objects.create(company_name="ACME Guard sem duplicata")
        Quotation.objects.create(number="COT-GUARD-UNICO", customer=customer, title="Único")
        mod._refuse_downgrade_if_duplicate_numbers(django_apps.apps, None)  # não levanta

    def test_com_number_repetido_levanta_runtimeerror_com_mensagem_clara(self):
        import django.apps as django_apps
        mod = self._migration_module()
        customer = Customer.objects.create(company_name="ACME Guard com duplicata")
        Quotation.objects.create(number="COT-GUARD-DUP", customer=customer, title="Rev.0")
        Quotation.objects.create(number="COT-GUARD-DUP", revision=1, customer=customer, title="Rev.1")
        with self.assertRaises(RuntimeError) as ctx:
            mod._refuse_downgrade_if_duplicate_numbers(django_apps.apps, None)
        self.assertIn("COT-GUARD-DUP", str(ctx.exception))
