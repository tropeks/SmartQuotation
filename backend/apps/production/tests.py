"""Testes de Ordem de Fabricação (H2.1) — TenantTestCase."""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.audit.services import approve_quotation, revoke_approval
from apps.production.models import (
    OrdemFabricacao, OFItem, OFMaterial, OFOperation,
    STATUS_ABERTA, STATUS_LIBERADA, STATUS_EM_PRODUCAO,
    STATUS_CONCLUIDA, STATUS_CANCELADA,
)
from apps.production import services
from apps.quotations.adapter import recompute
from apps.quotations.models import CalculationSnapshot, Customer
from apps.quotations.services import create_calculation_snapshot, create_feixe_quotation


class OrdemFabricacaoTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")
        self.user = User.objects.create_user(username="eng")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng PE", role="engenheiro",
            crea_number="CREA-123", crea_state="SP",
        )
        # D1: require active TechnicalApproval
        self.approval = approve_quotation(self.quotation, self.engineer)

    def _request(self):
        request = RequestFactory().post("/ofs/", REMOTE_ADDR="127.0.0.1")
        request.user = self.user
        return request

    def test_convert_copia_bom_e_roteiro(self):
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        self.assertIsInstance(of, OrdemFabricacao)
        self.assertEqual(of.status, STATUS_ABERTA)
        # BOM e roteiro copiados — pelo menos um item deve ter materiais ou operações
        self.assertTrue(of.itens.exists())
        has_bom_or_routing = any(
            of_item.materiais.exists() or of_item.operacoes.exists()
            for of_item in of.itens.all()
        )
        self.assertTrue(has_bom_or_routing, "Nenhum item da OF tem materiais ou operações copiados")

    def test_convert_registra_snapshot_hash(self):
        snapshot = self.quotation.snapshots.order_by("-created_at").first()
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        self.assertEqual(of.snapshot_hash, snapshot.snapshot_hash)
        self.assertEqual(of.calculation_snapshot_id, snapshot.pk)

    def test_of_numbering_sequential(self):
        of1 = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        # create second quotation with its own approval
        q2 = create_feixe_quotation(self.customer, "Feixe 2")
        approve_quotation(q2, self.engineer)
        of2 = services.convert_quotation_to_of(q2, created_by=self.user)
        n1 = int(of1.number.split("-")[-1])
        n2 = int(of2.number.split("-")[-1])
        self.assertEqual(n2, n1 + 1)

    def test_convert_bloqueia_sem_snapshot(self):
        self.quotation.snapshots.all().delete()
        with self.assertRaises(ValidationError):
            services.convert_quotation_to_of(self.quotation, created_by=self.user)

    def test_deep_copy_isolation_from_revision(self):
        """OF rows devem permanecer inalteradas após recompute() da cotação."""
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        original_item_count = of.itens.count()
        original_items = list(of.itens.values("codigo_item", "descricao", "custo_material", "custo_mo"))

        # Simulate a revision: recompute deletes+rebuilds EAP rows
        recompute(self.quotation)
        create_calculation_snapshot(self.quotation)

        # OF rows must be unchanged
        of.refresh_from_db()
        self.assertEqual(of.itens.count(), original_item_count)
        current_items = list(of.itens.values("codigo_item", "descricao", "custo_material", "custo_mo"))
        self.assertEqual(current_items, original_items)

    def test_status_transitions_validas(self):
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        self.assertEqual(of.status, STATUS_ABERTA)
        self.assertIsNone(of.released_at)

        services.liberar(of)
        of.refresh_from_db()
        self.assertEqual(of.status, STATUS_LIBERADA)
        self.assertIsNotNone(of.released_at)

        services.iniciar_producao(of)
        of.refresh_from_db()
        self.assertEqual(of.status, STATUS_EM_PRODUCAO)
        self.assertIsNotNone(of.started_at)

        services.concluir(of)
        of.refresh_from_db()
        self.assertEqual(of.status, STATUS_CONCLUIDA)
        self.assertIsNotNone(of.completed_at)

    def test_status_transition_invalida(self):
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        # aberta → concluida is invalid
        with self.assertRaises(ValidationError):
            services.concluir(of)
        # Once concluida, no transitions
        services.liberar(of)
        services.iniciar_producao(of)
        services.concluir(of)
        of.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.liberar(of)

    def test_cancelar_de_qualquer_estado(self):
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        # cancelar from aberta
        services.cancelar(of)
        of.refresh_from_db()
        self.assertEqual(of.status, STATUS_CANCELADA)
        self.assertIsNotNone(of.cancelled_at)

    def test_transition_registra_autoria(self):
        """Cada transição grava o autor (by) no campo *_by correspondente."""
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        services.liberar(of, by=self.user)
        of.refresh_from_db()
        self.assertEqual(of.released_by, self.user)
        services.iniciar_producao(of, by=self.user)
        of.refresh_from_db()
        self.assertEqual(of.started_by, self.user)
        services.concluir(of, by=self.user)
        of.refresh_from_db()
        self.assertEqual(of.completed_by, self.user)

    def test_convert_grava_access_log(self):
        of = services.convert_quotation_to_of(
            self.quotation, created_by=self.user, request=self._request()
        )
        self.assertTrue(
            AccessLog.objects.filter(
                action="convert",
                resource_type="OrdemFabricacao",
                resource_id=str(of.pk),
            ).exists()
        )

    def test_convert_bloqueia_of_duplicada(self):
        services.convert_quotation_to_of(self.quotation, created_by=self.user)
        with self.assertRaises(ValidationError):
            services.convert_quotation_to_of(self.quotation, created_by=self.user)

    def test_convert_exige_aprovacao_tecnica(self):
        # new quotation without approval — should fail
        q2 = create_feixe_quotation(self.customer, "Feixe Sem Aprovacao")
        with self.assertRaises(ValidationError):
            services.convert_quotation_to_of(q2, created_by=self.user)
        # with approval — should succeed
        approve_quotation(q2, self.engineer)
        of = services.convert_quotation_to_of(q2, created_by=self.user)
        self.assertIsNotNone(of.pk)

    def test_convert_bloqueia_aprovacao_revogada(self):
        """D1: aprovação revogada não permite converter."""
        revoke_approval(self.approval, self.engineer)
        with self.assertRaises(ValidationError):
            services.convert_quotation_to_of(self.quotation, created_by=self.user)

    def test_convert_bloqueia_hash_desatualizado(self):
        """D1: snapshot mais novo (hash diferente) sem aprovação correspondente bloqueia."""
        CalculationSnapshot.objects.create(
            quotation=self.quotation, snapshot_hash="deadbeef" * 8,
            inputs={}, outputs={}, engine_version="test", standard_refs=[],
        )
        with self.assertRaises(ValidationError):
            services.convert_quotation_to_of(self.quotation, created_by=self.user)

    def test_transition_grava_access_log(self):
        """D4: transição de status grava AccessLog action='transition'."""
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        services.liberar(of, request=self._request())
        self.assertTrue(
            AccessLog.objects.filter(
                action="transition",
                resource_type="OrdemFabricacao",
                resource_id=str(of.pk),
            ).exists()
        )

    def test_of_totais_snapshot(self):
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        # A OF reflete os totais PERSISTIDOS da cotação (arredondados pelo campo Decimal),
        # não o objeto em memória — refresca para comparar com o estado de banco.
        self.quotation.refresh_from_db()
        self.assertEqual(of.custo_material, self.quotation.custo_material)
        self.assertEqual(of.custo_mo, self.quotation.custo_mo)
        self.assertEqual(of.custo_total, self.quotation.custo_total)
        self.assertEqual(of.preco_com_impostos, self.quotation.preco_com_impostos)
        self.assertEqual(of.peso_bruto_kg, self.quotation.peso_bruto_kg)
        self.assertEqual(of.peso_liquido_kg, self.quotation.peso_liquido_kg)


class ApontamentoTests(TenantTestCase):
    def setUp(self):
        from datetime import date
        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")
        self.user = User.objects.create_user(username="op1")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_ap"), full_name="Eng",
            role="engenheiro", crea_number="CREA-9", crea_state="SP")
        approve_quotation(self.quotation, self.engineer)
        self.of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        services.liberar(self.of, by=self.user)
        self.op = OFOperation.objects.filter(item__ordem=self.of).first()
        self.today = date.today()

    def _request(self):
        request = RequestFactory().post("/ofs/", REMOTE_ADDR="127.0.0.1")
        request.user = self.user
        return request

    def test_log_entry_cria_e_soma(self):
        from decimal import Decimal
        services.log_production_entry(self.op, self.user, Decimal("3.0"), Decimal("0"), self.today)
        services.log_production_entry(self.op, self.user, Decimal("2.5"), Decimal("0"), self.today)
        self.op.refresh_from_db()
        self.assertEqual(self.op.entries.count(), 2)
        self.assertEqual(self.op.actual_hh, Decimal("5.5"))

    def test_log_entry_bloqueado_em_of_aberta(self):
        from decimal import Decimal
        q2 = create_feixe_quotation(self.customer, "Feixe B")
        approve_quotation(q2, self.engineer)
        of_aberta = services.convert_quotation_to_of(q2, created_by=self.user)  # status 'aberta'
        op_aberta = OFOperation.objects.filter(item__ordem=of_aberta).first()
        with self.assertRaises(ValidationError):
            services.log_production_entry(op_aberta, self.user, Decimal("1.0"), Decimal("0"), self.today)

    def test_log_entry_grava_access_log(self):
        from decimal import Decimal
        from apps.audit.models import AccessLog
        services.log_production_entry(self.op, self.user, Decimal("1.0"), Decimal("0"), self.today,
                                      request=self._request())
        self.assertTrue(AccessLog.objects.filter(action="appoint").exists())


class FechamentoTests(TenantTestCase):
    def setUp(self):
        from datetime import date
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="op")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_fech"), full_name="Eng",
            role="engenheiro", crea_number="CREA-7", crea_state="SP")
        self.today = date.today()

    def _of_em_producao(self, titulo):
        q = create_feixe_quotation(self.customer, titulo)
        approve_quotation(q, self.engineer)
        of = services.convert_quotation_to_of(q, created_by=self.user)
        services.liberar(of, by=self.user)
        services.iniciar_producao(of, by=self.user)
        return of

    def test_fechamento_grava_observacao_so_com_apontamento(self):
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe C")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0).first()
        services.log_production_entry(op, self.user, Decimal("10"), Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.filter(ordem=of)
        self.assertEqual(obs.count(), 1)  # só a operação apontada (leniente)
        self.assertEqual(obs.first().operacao, op.codigo_op)

    def test_fechamento_calcula_observed_rate(self):
        from decimal import Decimal
        from apps.production.models import ActualRate, ProductionObservation
        of = self._of_em_producao("Feixe D")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0).first()
        services.log_production_entry(op, self.user, Decimal("10"), Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.get(ordem=of, operacao=op.codigo_op)
        expected = (op.custo / Decimal("10")).quantize(Decimal("0.01"))
        self.assertEqual(obs.observed_rate, expected)
        ar = ActualRate.objects.get(operacao=op.codigo_op)
        self.assertEqual(ar.sample_count, 1)
        self.assertAlmostEqual(float(ar.mean_rate), float(expected), places=2)

    def test_fechamento_ignora_actual_hh_zero(self):
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe E")
        # nenhuma operação apontada -> nenhuma observação, sem div/0
        services.concluir(of, by=self.user)
        self.assertEqual(ProductionObservation.objects.filter(ordem=of).count(), 0)


class ApontamentoViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="opv", password="x")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_v"), full_name="Eng",
            role="engenheiro", crea_number="CREA-5", crea_state="SP")
        self.q = create_feixe_quotation(self.customer, "Feixe")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)
        services.liberar(self.of, by=self.user)
        self.op = OFOperation.objects.filter(item__ordem=self.of).first()

    def test_appoint_view_cria_entry(self):
        from apps.production.models import ProductionEntry
        self.client.force_login(self.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "2.5", "hours_hm": "0", "entry_date": "2026-06-23", "notes": "turno A"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ProductionEntry.objects.filter(of_operation=self.op).exists())


class ActualRateMathTests(TenantTestCase):
    def test_welford_agrega_amostras(self):
        from decimal import Decimal
        from apps.production.models import ActualRate
        # três R$/h observados: 100, 200, 300 -> mean 200
        for r in (Decimal("100"), Decimal("200"), Decimal("300")):
            services._update_actual_rate("FURAR_ESPELHO", r)
        ar = ActualRate.objects.get(operacao="FURAR_ESPELHO")
        self.assertEqual(ar.sample_count, 3)
        self.assertAlmostEqual(float(ar.mean_rate), 200.0, places=2)
        self.assertGreater(float(ar.confidence), 0.0)
        self.assertLessEqual(float(ar.confidence), 1.0)

    def test_confidence_valor_exato(self):
        """Welford com 3 amostras (100,200,300): mean≈200, confidence≈0.0888."""
        from decimal import Decimal
        from apps.production.models import ActualRate
        for v in (100, 200, 300):
            services._update_actual_rate("OP-X", Decimal(v))
        ar = ActualRate.objects.get(operacao="OP-X")
        # stddev=81.6497, mean=200, cv≈0.40825, n=3
        # confidence=(1-0.40825)*(3/20)=0.08876
        self.assertAlmostEqual(float(ar.mean_rate), 200.0, places=3)
        self.assertAlmostEqual(float(ar.confidence), 0.0888, places=3)


class FechamentoExtrasTests(TenantTestCase):
    """Casos adicionais de fechamento cobrindo os achados da revisão."""

    def setUp(self):
        from datetime import date
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="op_fx")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_fx"), full_name="Eng",
            role="engenheiro", crea_number="CREA-8", crea_state="SP")
        self.today = date.today()

    def _of_em_producao(self, titulo):
        q = create_feixe_quotation(self.customer, titulo)
        approve_quotation(q, self.engineer)
        of = services.convert_quotation_to_of(q, created_by=self.user)
        services.liberar(of, by=self.user)
        services.iniciar_producao(of, by=self.user)
        return of

    def test_fechamento_ignora_custo_zero(self):
        """Op com custo=0 não gera ProductionObservation mesmo com apontamento."""
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe CZ")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0).first()
        services.log_production_entry(op, self.user, Decimal("5"), Decimal("0"), self.today)
        # Zero out cost before closing
        op.custo = 0
        op.save()
        services.concluir(of, by=self.user)
        self.assertFalse(
            ProductionObservation.objects.filter(ordem=of, operacao=op.codigo_op).exists()
        )

    def test_duas_ofs_incrementam_n(self):
        """Dois fechamentos de OFs com a mesma operação geram sample_count=2 no ActualRate."""
        from decimal import Decimal
        from apps.production.models import ActualRate
        of1 = self._of_em_producao("Feixe N1")
        of2 = self._of_em_producao("Feixe N2")
        # Pick the same codigo_op from both OFs
        op1 = OFOperation.objects.filter(item__ordem=of1, custo__gt=0).first()
        target_codigo = op1.codigo_op
        op2 = OFOperation.objects.filter(item__ordem=of2, codigo_op=target_codigo, custo__gt=0).first()
        self.assertIsNotNone(op2, f"Operação {target_codigo} não encontrada na segunda OF")
        services.log_production_entry(op1, self.user, Decimal("8"), Decimal("0"), self.today)
        services.concluir(of1, by=self.user)
        services.log_production_entry(op2, self.user, Decimal("8"), Decimal("0"), self.today)
        services.concluir(of2, by=self.user)
        ar = ActualRate.objects.get(operacao=target_codigo)
        self.assertEqual(ar.sample_count, 2)

    def test_reconcluir_nao_duplica(self):
        """Tentar concluir OF já concluída levanta ValidationError; count de observações não muda."""
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe RC")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0).first()
        services.log_production_entry(op, self.user, Decimal("10"), Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        count_before = ProductionObservation.objects.filter(ordem=of).count()
        self.assertGreater(count_before, 0)
        with self.assertRaises(ValidationError):
            services.concluir(of, by=self.user)
        self.assertEqual(ProductionObservation.objects.filter(ordem=of).count(), count_before)


class ApontamentoValidacaoViewTests(TenantTestCase):
    """Testes de validação de input na view de apontamento."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="opval", password="x")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_val"), full_name="Eng",
            role="engenheiro", crea_number="CREA-6", crea_state="SP")
        self.q = create_feixe_quotation(self.customer, "Feixe Val")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)
        services.liberar(self.of, by=self.user)
        self.op = OFOperation.objects.filter(item__ordem=self.of).first()

    def test_appoint_view_horas_invalidas(self):
        """POST com hours_hh='abc' retorna 302 sem criar ProductionEntry."""
        from apps.production.models import ProductionEntry
        self.client.force_login(self.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "abc", "hours_hm": "0", "entry_date": "2026-06-23"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())

    def test_appoint_view_horas_negativas(self):
        """POST com hours_hh='-1' retorna 302 sem criar ProductionEntry."""
        from apps.production.models import ProductionEntry
        self.client.force_login(self.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "-1", "hours_hm": "0", "entry_date": "2026-06-23"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())
