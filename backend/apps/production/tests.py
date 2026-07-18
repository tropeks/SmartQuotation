"""Testes de Ordem de Fabricação (H2.1) — TenantTestCase."""
import sys
import types
from unittest import mock
from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.audit.services import approve_quotation, revoke_approval
from apps.integrations.nomus.models import NomusIntegrationConfig, NomusSyncRun
from apps.integrations.protheus.models import ProtheusIntegrationConfig, ProtheusSyncRun
from apps.integrations.sap_b1.models import SapB1IntegrationConfig, SapB1SyncRun
from apps.production.models import (
    OrdemFabricacao, OFItem, OFMaterial, OFOperation,
    InspectionItem, InspectionPlan,
    STATUS_ABERTA, STATUS_LIBERADA, STATUS_EM_PRODUCAO,
    STATUS_CONCLUIDA, STATUS_CANCELADA,
)
from apps.production import services
from apps.production.admin import OrdemFabricacaoAdmin
from apps.quotations.adapter import recompute
from apps.quotations.models import CalculationSnapshot, Customer, ItemOperation
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

    def test_convert_copia_campos_editaveis_da_operacao(self):
        op = ItemOperation.objects.filter(item__quotation=self.quotation).order_by("id").first()
        op.horas_hh = Decimal("3.50")
        op.horas_hm = Decimal("1.25")
        op.taxa_hora = Decimal("120.00")
        op.taxa_hora_hm = Decimal("80.00")
        op.custo_direto = False
        op.save(
            update_fields=["horas_hh", "horas_hm", "taxa_hora", "taxa_hora_hm", "custo_direto"]
        )
        create_calculation_snapshot(self.quotation)
        approve_quotation(self.quotation, self.engineer)

        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        of_op = OFOperation.objects.get(item__ordem=of, codigo_op=op.codigo_op)

        self.assertEqual(of_op.horas_hh, op.horas_hh)
        self.assertEqual(of_op.horas_hm, op.horas_hm)
        self.assertEqual(of_op.taxa_hora, op.taxa_hora)
        self.assertEqual(of_op.taxa_hora_hm, op.taxa_hora_hm)
        self.assertEqual(of_op.custo_direto, op.custo_direto)

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

    @mock.patch("apps.integrations.protheus.services.enqueue_sync_run_async")
    def test_liberar_enfileira_export_protheus_quando_habilitado(self, enqueue_sync_run_async):
        ProtheusIntegrationConfig.objects.create(
            enabled=True,
            base_url="https://protheus.example/api",
            company_code="01",
            branch_code="01",
            export_on_release=True,
        )
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)

        run = ProtheusSyncRun.objects.get(
            direction=ProtheusSyncRun.DIRECTION_PUSH,
            entity_type="work_order",
            local_id=str(of.pk),
        )
        enqueue_sync_run_async.assert_called_once()
        self.assertEqual(enqueue_sync_run_async.call_args.args[0].pk, run.pk)

    @mock.patch("apps.integrations.protheus.services.enqueue_sync_run_async")
    def test_liberar_nao_enfileira_export_quando_desabilitado(self, enqueue_sync_run_async):
        ProtheusIntegrationConfig.objects.create(
            enabled=True,
            base_url="https://protheus.example/api",
            company_code="01",
            branch_code="01",
            export_on_release=False,
        )
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)

        self.assertFalse(ProtheusSyncRun.objects.exists())
        enqueue_sync_run_async.assert_not_called()

    @mock.patch("apps.integrations.sap_b1.services.enqueue_sync_run_async")
    def test_liberar_enfileira_export_sap_b1_quando_habilitado(self, enqueue_sync_run_async):
        SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sap.example/b1s/v2",
            company_db="ENGEMATEX",
            sync_sales_orders_enabled=True,
            sync_boms_enabled=True,
        )
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)

        so_run = SapB1SyncRun.objects.get(entity_type="sales_order", local_id=str(of.pk))
        bom_run = SapB1SyncRun.objects.get(entity_type="bom", local_id=str(of.pk))
        self.assertEqual(enqueue_sync_run_async.call_count, 2)
        called_pks = {c.args[0].pk for c in enqueue_sync_run_async.call_args_list}
        self.assertEqual(called_pks, {so_run.pk, bom_run.pk})

    @mock.patch("apps.integrations.sap_b1.services.enqueue_sync_run_async")
    def test_liberar_nao_enfileira_sap_b1_quando_desabilitado(self, enqueue_sync_run_async):
        SapB1IntegrationConfig.objects.create(
            enabled=False,
            base_url="https://sap.example/b1s/v2",
            company_db="ENGEMATEX",
        )
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)

        self.assertFalse(SapB1SyncRun.objects.exists())
        enqueue_sync_run_async.assert_not_called()

    @mock.patch("apps.integrations.nomus.services.enqueue_sync_run_async")
    def test_liberar_enfileira_export_nomus_quando_ativo(self, enqueue_sync_run_async):
        NomusIntegrationConfig.objects.create(enabled=True, base_url="", access_key="")
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)

        run = NomusSyncRun.objects.get(entity_type=NomusSyncRun.ENTITY_PRODUCTION_ORDER)
        self.assertEqual(run.payload.get("order_number"), of.number)
        enqueue_sync_run_async.assert_called_once()
        self.assertEqual(enqueue_sync_run_async.call_args.args[0].pk, run.pk)

    @mock.patch("apps.integrations.nomus.services.enqueue_sync_run_async")
    @mock.patch("apps.integrations.sap_b1.services.enqueue_sync_run_async")
    def test_liberar_com_sap_b1_ativo_usa_sap_b1_e_nao_dispara_nomus(
        self, sap_b1_enqueue_sync_run_async, nomus_enqueue_sync_run_async
    ):
        SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sap.example/b1s/v2",
            company_db="ENGEMATEX",
            sync_sales_orders_enabled=True,
            sync_boms_enabled=True,
        )
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)

        self.assertTrue(SapB1SyncRun.objects.filter(local_id=str(of.pk)).exists())
        self.assertFalse(NomusSyncRun.objects.exists())
        sap_b1_enqueue_sync_run_async.assert_called()
        nomus_enqueue_sync_run_async.assert_not_called()

    @mock.patch("apps.integrations.nomus.services.enqueue_sync_run_async")
    def test_reexport_manual_nomus_cria_novo_run(self, enqueue_sync_run_async):
        NomusIntegrationConfig.objects.create(enabled=True, base_url="", access_key="")
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)

        with self.captureOnCommitCallbacks(execute=True):
            services.liberar(of, by=self.user)
        self.assertEqual(NomusSyncRun.objects.count(), 1)

        with self.captureOnCommitCallbacks(execute=True):
            new_run = services.reexport_nomus(of, by=self.user, request=self._request())

        self.assertEqual(NomusSyncRun.objects.count(), 2)
        self.assertIsNotNone(new_run)
        self.assertEqual(enqueue_sync_run_async.call_count, 2)
        self.assertTrue(
            AccessLog.objects.filter(action="nomus_reexport", resource_id=str(of.pk)).exists()
        )

    def _fake_sap_b1_services(self, run=None, enqueue_ok=True):
        sap_b1_pkg = types.ModuleType("apps.integrations.sap_b1")
        sap_b1_services = types.ModuleType("apps.integrations.sap_b1.services")
        sap_b1_services.maybe_enqueue_sales_order_sync = mock.Mock(return_value=run)
        sap_b1_services.enqueue_sales_order_sync = mock.Mock(return_value=(run, True))
        sap_b1_services.maybe_enqueue_bom_sync = mock.Mock(return_value=run)
        sap_b1_services.enqueue_bom_sync = mock.Mock(return_value=(run, True))
        sap_b1_services.enqueue_sync_run_async = mock.Mock(return_value=enqueue_ok)
        sap_b1_pkg.services = sap_b1_services
        return sap_b1_pkg, sap_b1_services

    def test_admin_action_exporta_of_para_sap_b1(self):
        fake_run = types.SimpleNamespace(pk=777)
        sap_b1_pkg, sap_b1_services = self._fake_sap_b1_services(run=fake_run, enqueue_ok=True)
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        request = RequestFactory().post("/admin/apps/production/ordemfabricacao/")
        request.user = self.user
        admin_instance = OrdemFabricacaoAdmin(OrdemFabricacao, admin.site)

        with mock.patch.dict(
            sys.modules,
            {
                "apps.integrations.sap_b1": sap_b1_pkg,
                "apps.integrations.sap_b1.services": sap_b1_services,
            },
        ):
            with mock.patch("apps.production.admin.import_module", return_value=sap_b1_services):
                with mock.patch.object(admin_instance, "message_user") as message_user:
                    admin_instance.export_to_sap_b1(request, OrdemFabricacao.objects.filter(pk=of.pk))

        sap_b1_services.maybe_enqueue_sales_order_sync.assert_called_once_with(of, trigger="admin")
        sap_b1_services.maybe_enqueue_bom_sync.assert_called_once_with(of, trigger="admin")
        self.assertEqual(sap_b1_services.enqueue_sync_run_async.call_count, 2)
        sap_b1_services.enqueue_sync_run_async.assert_any_call(
            fake_run,
            schema_name=services.connection.schema_name,
        )
        sap_b1_services.enqueue_sync_run_async.assert_any_call(
            fake_run,
            schema_name=services.connection.schema_name,
        )
        message_user.assert_called_once()

    def test_admin_action_exporta_of_para_sap_b1_usa_primeira_api_disponivel(self):
        fake_run = types.SimpleNamespace(pk=778)
        sap_b1_pkg, sap_b1_services = self._fake_sap_b1_services(run=fake_run, enqueue_ok=True)
        delattr(sap_b1_services, "maybe_enqueue_sales_order_sync")
        delattr(sap_b1_services, "maybe_enqueue_bom_sync")
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        request = RequestFactory().post("/admin/apps/production/ordemfabricacao/")
        request.user = self.user
        admin_instance = OrdemFabricacaoAdmin(OrdemFabricacao, admin.site)

        with mock.patch.dict(
            sys.modules,
            {
                "apps.integrations.sap_b1": sap_b1_pkg,
                "apps.integrations.sap_b1.services": sap_b1_services,
            },
        ):
            with mock.patch("apps.production.admin.import_module", return_value=sap_b1_services):
                with mock.patch.object(admin_instance, "message_user"):
                    admin_instance.export_to_sap_b1(request, OrdemFabricacao.objects.filter(pk=of.pk))

        sap_b1_services.enqueue_sales_order_sync.assert_called_once_with(of, trigger="admin")
        sap_b1_services.enqueue_bom_sync.assert_called_once_with(of, trigger="admin")
        self.assertEqual(sap_b1_services.enqueue_sync_run_async.call_count, 2)
        sap_b1_services.enqueue_sync_run_async.assert_any_call(
            fake_run,
            schema_name=services.connection.schema_name,
        )
        sap_b1_services.enqueue_sync_run_async.assert_any_call(
            fake_run,
            schema_name=services.connection.schema_name,
        )

    def test_admin_action_nao_republica_run_sap_b1_ja_concluido(self):
        completed_run = types.SimpleNamespace(pk=779, status="success")
        sap_b1_pkg, sap_b1_services = self._fake_sap_b1_services(run=completed_run, enqueue_ok=True)
        sap_b1_services.maybe_enqueue_sales_order_sync.return_value = (completed_run, False)
        sap_b1_services.maybe_enqueue_bom_sync.return_value = (completed_run, False)
        of = services.convert_quotation_to_of(self.quotation, created_by=self.user)
        request = RequestFactory().post("/admin/apps/production/ordemfabricacao/")
        request.user = self.user
        admin_instance = OrdemFabricacaoAdmin(OrdemFabricacao, admin.site)

        with mock.patch.dict(
            sys.modules,
            {
                "apps.integrations.sap_b1": sap_b1_pkg,
                "apps.integrations.sap_b1.services": sap_b1_services,
            },
        ):
            with mock.patch("apps.production.admin.import_module", return_value=sap_b1_services):
                with mock.patch.object(admin_instance, "message_user") as message_user:
                    admin_instance.export_to_sap_b1(request, OrdemFabricacao.objects.filter(pk=of.pk))

        sap_b1_services.maybe_enqueue_sales_order_sync.assert_called_once_with(of, trigger="admin")
        sap_b1_services.maybe_enqueue_bom_sync.assert_called_once_with(of, trigger="admin")
        sap_b1_services.enqueue_sync_run_async.assert_not_called()
        message_user.assert_called_once()

    def test_admin_healthcheck_route_delega_para_sap_b1(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        staff_user = User.objects.create_user(username="admin_sap_b1", password="x")
        staff_user.is_staff = True
        staff_user.is_superuser = True
        staff_user.save(update_fields=["is_staff", "is_superuser"])
        fake_views = types.SimpleNamespace(
            admin_healthcheck=mock.Mock(return_value=JsonResponse({"ok": True, "source": "sap_b1"}))
        )

        with mock.patch("smartquotation.urls.import_module", return_value=fake_views):
            self.client.force_login(staff_user)
            response = self.client.get("/admin/sap-b1/health/")

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True, "source": "sap_b1"})
        fake_views.admin_healthcheck.assert_called_once()



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

    def _fake_omie_services(self, run=None):
        omie_pkg = types.ModuleType("apps.integrations.omie")
        omie_services = types.ModuleType("apps.integrations.omie.services")
        omie_services.maybe_enqueue_nfe_issue = mock.Mock(return_value=run)
        omie_services.enqueue_invoice_run_async = mock.Mock()
        omie_pkg.services = omie_services
        return omie_pkg, omie_services

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

    def test_concluir_com_omie_habilitado_enfileira_run_pos_commit(self):
        of = self._of_em_producao("Feixe F")
        fake_run = types.SimpleNamespace(pk=321)
        omie_pkg, omie_services = self._fake_omie_services(run=fake_run)

        with mock.patch.dict(
            sys.modules,
            {
                "apps.integrations.omie": omie_pkg,
                "apps.integrations.omie.services": omie_services,
            },
        ):
            with self.captureOnCommitCallbacks(execute=True):
                services.concluir(of, by=self.user)

        omie_services.maybe_enqueue_nfe_issue.assert_called_once_with(of, trigger="of_completed")
        omie_services.enqueue_invoice_run_async.assert_called_once_with(
            fake_run,
            schema_name=services.connection.schema_name,
        )

    def test_concluir_com_omie_desabilitado_nao_enfileira(self):
        of = self._of_em_producao("Feixe G")
        omie_pkg, omie_services = self._fake_omie_services(run=None)

        with mock.patch.dict(
            sys.modules,
            {
                "apps.integrations.omie": omie_pkg,
                "apps.integrations.omie.services": omie_services,
            },
        ):
            with self.captureOnCommitCallbacks(execute=True):
                services.concluir(of, by=self.user)

        omie_services.maybe_enqueue_nfe_issue.assert_called_once_with(of, trigger="of_completed")
        omie_services.enqueue_invoice_run_async.assert_not_called()

    def test_transicao_invalida_nao_cria_run_omie(self):
        q = create_feixe_quotation(self.customer, "Feixe H")
        approve_quotation(q, self.engineer)
        of = services.convert_quotation_to_of(q, created_by=self.user)
        omie_pkg, omie_services = self._fake_omie_services(run=types.SimpleNamespace(pk=999))

        with mock.patch.dict(
            sys.modules,
            {
                "apps.integrations.omie": omie_pkg,
                "apps.integrations.omie.services": omie_services,
            },
        ):
            with self.assertRaises(ValidationError):
                services.concluir(of, by=self.user)

        omie_services.maybe_enqueue_nfe_issue.assert_not_called()
        omie_services.enqueue_invoice_run_async.assert_not_called()


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
        self.client.force_login(self.engineer.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "2.5", "hours_hm": "0", "entry_date": "2026-06-23", "notes": "turno A"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ProductionEntry.objects.filter(of_operation=self.op).exists())

    def test_appoint_view_bloqueia_orcamentista(self):
        from datetime import date
        from apps.production.models import ProductionEntry
        orc_user = User.objects.create_user(username="orc_appoint", password="x")
        UserProfile.objects.create(
            user=orc_user, full_name="Orcamentista", role=UserProfile.ROLE_ORCAMENTISTA,
        )
        self.client.force_login(orc_user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "2.0", "hours_hm": "0", "entry_date": str(date.today())},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())


class OFAuthorizationViewTests(TenantTestCase):
    """
    Autorização das views de conversão e transição de OF.

    Regressão do achado /cso 2026-07-17: ambas carregavam só @login_required, então
    o viewer (papel dedicado de somente-leitura) conseguia cancelar OF — estado
    terminal — e converter cotação em OF, disparando os exports de ERP e, via
    `concluir`, a emissão de NF-e. Não há backstop em services.py: ele valida a
    máquina de estados e as pré-condições de negócio, nunca o papel do chamador.
    """

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.eng_user = User.objects.create_user(username="eng_authz", password="x")
        self.engineer = UserProfile.objects.create(
            user=self.eng_user, full_name="Eng Authz", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-77", crea_state="SP",
        )
        self.q = create_feixe_quotation(self.customer, "Feixe Authz")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.eng_user)

    def _profile(self, username, role):
        user = User.objects.create_user(username=username, password="x")
        UserProfile.objects.create(user=user, full_name=username, role=role)
        return user

    def test_transicao_bloqueia_viewer(self):
        """Viewer é somente-leitura: cancelar é terminal e irreversível pela app."""
        self.client.force_login(self._profile("viewer_cancel", UserProfile.ROLE_VIEWER))
        resp = self.client.post(f"/ofs/{self.of.pk}/transicao/", {"action": "cancelar"})
        self.assertEqual(resp.status_code, 403)
        self.of.refresh_from_db()
        self.assertEqual(self.of.status, STATUS_ABERTA)

    def test_transicao_bloqueia_orcamentista(self):
        self.client.force_login(self._profile("orc_transicao", UserProfile.ROLE_ORCAMENTISTA))
        resp = self.client.post(f"/ofs/{self.of.pk}/transicao/", {"action": "liberar"})
        self.assertEqual(resp.status_code, 403)
        self.of.refresh_from_db()
        self.assertEqual(self.of.status, STATUS_ABERTA)

    def test_transicao_permite_engenheiro(self):
        self.client.force_login(self.eng_user)
        resp = self.client.post(f"/ofs/{self.of.pk}/transicao/", {"action": "liberar"})
        self.assertEqual(resp.status_code, 302)
        self.of.refresh_from_db()
        self.assertEqual(self.of.status, STATUS_LIBERADA)

    def test_converter_bloqueia_viewer(self):
        q2 = create_feixe_quotation(self.customer, "Feixe Conv Viewer")
        approve_quotation(q2, self.engineer)
        self.client.force_login(self._profile("viewer_conv", UserProfile.ROLE_VIEWER))
        resp = self.client.post(f"/cotacoes/{q2.pk}/converter-of/")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(q2.ordens_fabricacao.exists())

    def test_converter_bloqueia_orcamentista(self):
        """Orçamentista monta a cotação mas não lança manufatura no ERP."""
        q2 = create_feixe_quotation(self.customer, "Feixe Conv Orc")
        approve_quotation(q2, self.engineer)
        self.client.force_login(self._profile("orc_conv", UserProfile.ROLE_ORCAMENTISTA))
        resp = self.client.post(f"/cotacoes/{q2.pk}/converter-of/")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(q2.ordens_fabricacao.exists())

    def test_converter_permite_gestor_comercial(self):
        q2 = create_feixe_quotation(self.customer, "Feixe Conv Gestor")
        approve_quotation(q2, self.engineer)
        self.client.force_login(self._profile("gestor_conv", UserProfile.ROLE_GESTOR_COMERCIAL))
        resp = self.client.post(f"/cotacoes/{q2.pk}/converter-of/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(q2.ordens_fabricacao.exists())

    def test_detalhe_nao_renderiza_acoes_para_viewer(self):
        """O botão 'Cancelar OF' era gateado por status, não por papel."""
        self.client.force_login(self._profile("viewer_detail", UserProfile.ROLE_VIEWER))
        resp = self.client.get(f"/ofs/{self.of.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_manage_of"])
        self.assertNotContains(resp, "Cancelar OF")

    def test_detalhe_renderiza_acoes_para_engenheiro(self):
        self.client.force_login(self.eng_user)
        resp = self.client.get(f"/ofs/{self.of.pk}/")
        self.assertTrue(resp.context["can_manage_of"])
        self.assertContains(resp, "Cancelar OF")


class OrdemFabricacaoDetailViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_detail", password="x")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng Detail", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-77", crea_state="SP",
        )
        self.q = create_feixe_quotation(self.customer, "Feixe Detail")
        op = ItemOperation.objects.filter(item__quotation=self.q).order_by("id").first()
        op.horas_hh = Decimal("3.50")
        op.horas_hm = Decimal("1.25")
        op.taxa_hora = Decimal("120.00")
        op.taxa_hora_hm = Decimal("80.00")
        op.custo_direto = False
        op.save(
            update_fields=["horas_hh", "horas_hm", "taxa_hora", "taxa_hora_hm", "custo_direto"]
        )
        create_calculation_snapshot(self.q)
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def test_detail_renderiza_horas_estimadas_da_operacao(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Horas est.")
        self.assertContains(response, "HH 3,50")
        self.assertContains(response, "HM 1,25")


class HourVarianceUITests(TenantTestCase):
    """SQ-COST-4: superfície de leitura do desvio horas orçado × real (SQ-COST-3).

    Observações são criadas diretamente (sem passar pelo fechamento real) para testar
    só a apresentação — não a computação de estimated_hh/delta_horas_pct, que é
    responsabilidade de services._close_out_observations (SQ-COST-3, não tocado aqui).
    """

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_hv")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng HV", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-90", crea_state="SP",
        )
        self.q = create_feixe_quotation(self.customer, "Feixe HV")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def _observation(self, operacao, estimated_hh, actual_hh, delta_horas_pct):
        from apps.production.models import ProductionObservation
        return ProductionObservation.objects.create(
            operacao=operacao, ordem=self.of,
            estimated_custo=Decimal("100.00"), actual_hh=Decimal(actual_hh),
            observed_rate=Decimal("10.00"), estimated_hh=Decimal(estimated_hh),
            delta_horas_pct=delta_horas_pct,
        )

    def test_detail_renderiza_secao_desvios_de_horas_quando_observations_existem(self):
        self._observation("SOLDA-01", "10.00", "12.50", Decimal("25.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Desvios de Horas")
        self.assertContains(response, "SOLDA-01")

    def test_detail_sem_observations_nao_renderiza_secao_e_nao_quebra(self):
        # regressão: OF recém-convertida, sem apontamento/fechamento -> sem observações
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Desvios de Horas")

    def test_delta_positivo_renderiza_badge_over(self):
        self._observation("SOLDA-01", "10.00", "12.50", Decimal("25.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertContains(response, "q-badge--over")
        self.assertContains(response, "+25,00%")

    def test_delta_negativo_renderiza_badge_under(self):
        self._observation("CORTE-02", "10.00", "6.00", Decimal("-40.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertContains(response, "q-badge--under")
        self.assertContains(response, "-40,00%")

    def test_delta_none_renderiza_sem_base_sem_crash(self):
        self._observation("SERV-FIXO", "0.00", "3.00", None)
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "q-badge--na")
        self.assertContains(response, "sem base")
        self.assertNotContains(response, "0,00%")

    def test_hour_variance_observations_ordenadas_por_maior_delta_absoluto(self):
        self._observation("OP-PEQUENO", "10.00", "10.50", Decimal("5.00"))
        self._observation("OP-GRANDE", "10.00", "6.00", Decimal("-40.00"))
        self._observation("OP-MEDIO", "10.00", "11.00", Decimal("10.00"))
        self._observation("OP-SEM-BASE", "0.00", "3.00", None)

        ordered = [obs.operacao for obs in self.of.hour_variance_observations]

        self.assertEqual(ordered, ["OP-GRANDE", "OP-MEDIO", "OP-PEQUENO", "OP-SEM-BASE"])

    def test_detail_renderiza_ordem_por_maior_desvio_absoluto(self):
        self._observation("OP-PEQUENO", "10.00", "10.50", Decimal("5.00"))
        self._observation("OP-GRANDE", "10.00", "6.00", Decimal("-40.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")
        content = response.content.decode()

        self.assertLess(content.index("OP-GRANDE"), content.index("OP-PEQUENO"))

    def test_hour_variance_observations_avaliada_uma_unica_vez_na_view(self):
        # SQ-COST-8 achado 3: a property era avaliada 2x no template (um {% if %} e um
        # {% for %}). A view agora computa uma vez e injeta a lista pronta no contexto.
        # Usa um retorno truthy (não []) para que o {% for %} realmente seja alcançado —
        # com [] o {% if %} já é falso e o for nunca reavalia a property (falso-positivo).
        obs = self._observation("SOLDA-01", "10.00", "12.50", Decimal("25.00"))
        self.client.force_login(self.user)

        with mock.patch(
            "apps.production.models.OrdemFabricacao.hour_variance_observations",
            new_callable=mock.PropertyMock,
            return_value=[obs],
        ) as mocked:
            response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked.call_count, 1)


class HourVarianceToleranceTests(TenantTestCase):
    """SQ-COST-5: tolerância/semáforo de ±5% sobre ProductionObservation.delta_horas_pct.

    Observações são criadas diretamente (mesmo padrão de HourVarianceUITests) para testar
    só a classificação/apresentação — não a computação de delta_horas_pct (SQ-COST-3,
    não tocado aqui).
    """

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_tol")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng Tol", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-92", crea_state="SP",
        )
        self.q = create_feixe_quotation(self.customer, "Feixe Tol")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def _observation(self, operacao, delta_horas_pct):
        from apps.production.models import ProductionObservation
        return ProductionObservation.objects.create(
            operacao=operacao, ordem=self.of,
            estimated_custo=Decimal("100.00"), actual_hh=Decimal("10.00"),
            observed_rate=Decimal("10.00"), estimated_hh=Decimal("10.00"),
            delta_horas_pct=delta_horas_pct,
        )

    def _get_detail(self):
        self.client.force_login(self.user)
        return self.client.get(f"/ofs/{self.of.pk}/")

    def test_delta_0_01_pct_dentro_da_tolerancia_nao_alerta(self):
        self._observation("OP-TOL-A", Decimal("0.01"))

        response = self._get_detail()

        self.assertContains(response, "dentro do esperado")
        self.assertNotContains(response, "q-badge--over")
        self.assertNotContains(response, "q-badge--under")

    def test_delta_exatamente_5_pct_dentro_da_tolerancia(self):
        self._observation("OP-TOL-B", Decimal("5.00"))

        response = self._get_detail()

        self.assertContains(response, "dentro do esperado")
        self.assertNotContains(response, "q-badge--over")

    def test_delta_exatamente_minus_5_pct_dentro_da_tolerancia(self):
        self._observation("OP-TOL-C", Decimal("-5.00"))

        response = self._get_detail()

        self.assertContains(response, "dentro do esperado")
        self.assertNotContains(response, "q-badge--under")

    def test_delta_5_01_pct_acima_da_tolerancia(self):
        self._observation("OP-TOL-D", Decimal("5.01"))

        response = self._get_detail()

        self.assertContains(response, "q-badge--over")
        self.assertContains(response, "acima da tolerância")

    def test_delta_minus_5_01_pct_abaixo_da_tolerancia(self):
        self._observation("OP-TOL-E", Decimal("-5.01"))

        response = self._get_detail()

        self.assertContains(response, "q-badge--under")
        self.assertContains(response, "abaixo da tolerância")

    def test_delta_none_continua_sem_base(self):
        self._observation("OP-TOL-F", None)

        response = self._get_detail()

        self.assertContains(response, "q-badge--na")
        self.assertContains(response, "sem base")

    def test_ui_menciona_tolerancia_de_5_porcento(self):
        self._observation("OP-TOL-G", Decimal("1.00"))

        response = self._get_detail()

        self.assertContains(response, "±5%")

    def test_tolerancia_vem_do_context_a_partir_de_tolerancia_horas_pct(self):
        # SQ-COST-8 achado 4: "±5%" não pode mais estar hardcoded no template — a view
        # deve derivar a string de exibição de ProductionObservation.TOLERANCIA_HORAS_PCT.
        self._observation("OP-TOL-CTX", Decimal("1.00"))

        response = self._get_detail()

        self.assertEqual(response.context["tolerancia_horas_pct"], "±5%")

    def test_model_hours_variance_status_classifica_corretamente(self):
        from apps.production.models import ProductionObservation

        casos = [
            (Decimal("0.01"), "dentro"),
            (Decimal("5.00"), "dentro"),
            (Decimal("-5.00"), "dentro"),
            (Decimal("5.01"), "acima"),
            (Decimal("-5.01"), "abaixo"),
            (None, "sem_base"),
        ]
        for delta, esperado in casos:
            obs = ProductionObservation(delta_horas_pct=delta)
            self.assertEqual(
                obs.hours_variance_status, esperado,
                msg=f"delta={delta} esperava {esperado}",
            )


class ProductionReviewSignalTests(TenantTestCase):
    """SQ-COST-6: sinal operacional de revisão de ProcessParameter.

    Agrega ProductionObservation.delta_horas_pct (SQ-COST-3) por operação e classifica
    candidatos a revisão da física (ProcessParameter) — SOMENTE LEITURA/analytics. Não
    recalcula delta_horas_pct, não altera ProcessParameter/Rate/ActualRate (Welford)/
    RateSuggestion nem pricing_engine. Observações são criadas diretamente (mesmo padrão
    de HourVarianceUITests/HourVarianceToleranceTests), não via fechamento real.
    """

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_signal")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng Signal", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-93", crea_state="SP",
        )
        self.q = create_feixe_quotation(self.customer, "Feixe Signal")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def _observation(self, operacao, delta_horas_pct):
        from apps.production.models import ProductionObservation
        return ProductionObservation.objects.create(
            operacao=operacao, ordem=self.of,
            estimated_custo=Decimal("100.00"), actual_hh=Decimal("10.00"),
            observed_rate=Decimal("10.00"), estimated_hh=Decimal("10.00"),
            delta_horas_pct=delta_horas_pct,
        )

    def test_insufficient_data_com_menos_de_3_observacoes(self):
        self._observation("OP-INSUF", Decimal("10.00"))
        self._observation("OP-INSUF", Decimal("12.00"))

        signal = services.production_review_signal()

        row = next(r for r in signal if r["operacao"] == "OP-INSUF")
        self.assertEqual(row["count"], 2)
        self.assertEqual(row["status"], "insufficient_data")

    def test_review_recommended_quando_media_abs_acima_de_5pct_com_3_amostras(self):
        self._observation("OP-REVISAR", Decimal("8.00"))
        self._observation("OP-REVISAR", Decimal("-9.00"))
        self._observation("OP-REVISAR", Decimal("7.00"))
        # média |Δ| = (8+9+7)/3 = 8.00 > 5.00 (TOLERANCIA_HORAS_PCT)

        signal = services.production_review_signal()

        row = next(r for r in signal if r["operacao"] == "OP-REVISAR")
        self.assertEqual(row["count"], 3)
        self.assertEqual(row["mean_abs_delta_pct"], Decimal("8.00"))
        self.assertEqual(row["status"], "review_recommended")
        flagged = [r["operacao"] for r in signal if r["status"] == "review_recommended"]
        self.assertIn("OP-REVISAR", flagged)

    def test_ok_quando_media_abs_dentro_da_tolerancia_com_3_amostras(self):
        self._observation("OP-OK", Decimal("2.00"))
        self._observation("OP-OK", Decimal("-3.00"))
        self._observation("OP-OK", Decimal("1.00"))
        # média |Δ| = (2+3+1)/3 = 2.00 <= 5.00

        signal = services.production_review_signal()

        row = next(r for r in signal if r["operacao"] == "OP-OK")
        self.assertEqual(row["status"], "ok")
        flagged = [r["operacao"] for r in signal if r["status"] == "review_recommended"]
        self.assertNotIn("OP-OK", flagged)

    def test_deltas_none_sao_ignorados_no_calculo_da_media(self):
        self._observation("OP-NONE", Decimal("10.00"))
        self._observation("OP-NONE", Decimal("10.00"))
        self._observation("OP-NONE", Decimal("10.00"))
        self._observation("OP-NONE", None)  # operação de valor fixo, sem base — ignorada
        self._observation("OP-NONE", None)

        signal = services.production_review_signal()

        row = next(r for r in signal if r["operacao"] == "OP-NONE")
        self.assertEqual(row["count"], 3)  # as 2 observações None não contam na amostra
        self.assertEqual(row["mean_abs_delta_pct"], Decimal("10.00"))
        self.assertEqual(row["status"], "review_recommended")

    def test_service_agrega_por_operacao_corretamente(self):
        self._observation("OP-A", Decimal("1.00"))
        self._observation("OP-A", Decimal("2.00"))
        self._observation("OP-B", Decimal("20.00"))
        self._observation("OP-B", Decimal("-25.00"))
        self._observation("OP-B", Decimal("22.00"))

        signal = services.production_review_signal()

        by_op = {r["operacao"]: r for r in signal}
        self.assertIn("OP-A", by_op)
        self.assertIn("OP-B", by_op)
        self.assertEqual(by_op["OP-A"]["count"], 2)
        self.assertEqual(by_op["OP-A"]["status"], "insufficient_data")
        self.assertEqual(by_op["OP-B"]["count"], 3)
        self.assertEqual(by_op["OP-B"]["status"], "review_recommended")

    def test_detail_renderiza_secao_de_sinal_para_operacao_flagged_da_propria_of(self):
        # usa o código de operação real do roteiro copiado da OF, para que a seção
        # apareça vinculada a esta OF especificamente (não é um relatório global solto)
        op = OFOperation.objects.filter(item__ordem=self.of).first()
        self._observation(op.codigo_op, Decimal("8.00"))
        self._observation(op.codigo_op, Decimal("-9.00"))
        self._observation(op.codigo_op, Decimal("7.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sinal de Revis")
        self.assertContains(response, op.codigo_op)

    def test_detail_nao_renderiza_secao_quando_nenhuma_operacao_flagged(self):
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sinal de Revis")

    def test_copy_da_secao_de_sinal_usa_frase_precisa_com_tolerancia(self):
        # SQ-COST-8 achado 2: "acima de ±5%" é impreciso pq o valor comparado já é
        # absoluto. Corrigido para "acima da tolerância (±5%)".
        op = OFOperation.objects.filter(item__ordem=self.of).first()
        self._observation(op.codigo_op, Decimal("8.00"))
        self._observation(op.codigo_op, Decimal("-9.00"))
        self._observation(op.codigo_op, Decimal("7.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertContains(response, "acima da tolerância (±5%)")
        self.assertNotContains(response, "acima de ±5%")


class ProcessParameterSuggestionTests(TenantTestCase):
    """SQ-COST-7: sugestão somente-leitura de novo ProcessParameter (física → horas)
    para operações 'review_recommended' (SQ-COST-6) — proposta manual, nunca aplicada
    automaticamente. Observações criadas diretamente (mesmo padrão de
    ProductionReviewSignalTests), não via fechamento real.
    """

    def setUp(self):
        from apps.engineering_params.models import ProcessParameter
        self.ProcessParameter = ProcessParameter
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_pp_suggestion")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng PP Suggestion", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-94", crea_state="SP",
        )
        self.q = create_feixe_quotation(self.customer, "Feixe PP Suggestion")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def _observation(self, operacao, delta_horas_pct, actual_hh=Decimal("10.00"),
                     estimated_hh=Decimal("10.00"), of_operation=None, ordem=None):
        from apps.production.models import ProductionObservation
        return ProductionObservation.objects.create(
            operacao=operacao, ordem=ordem or self.of, of_operation=of_operation,
            estimated_custo=Decimal("100.00"), actual_hh=actual_hh,
            observed_rate=Decimal("10.00"), estimated_hh=estimated_hh,
            delta_horas_pct=delta_horas_pct,
        )

    def _op_com_metodo(self, codigo_op, metodo="radial"):
        of_item = OFItem.objects.create(ordem=self.of, codigo_item="IT-PP", descricao="Item PP")
        return OFOperation.objects.create(
            item=of_item, codigo_op=codigo_op, descricao="Operação PP", metodo=metodo,
            custo=Decimal("100.00"), horas_hh=Decimal("10.00"),
        )

    def test_proposed_value_e_current_vezes_factor_com_mapeamento_disponivel(self):
        op = self._op_com_metodo("OP-PP-MAP")
        self.ProcessParameter.objects.create(
            operacao=op.codigo_op, metodo="radial", material=None, valor=Decimal("40.0000"),
            unidade="mm/min", descricao="avanço teste",
        )
        # 3 observações fechadas, todas actual=12.00 / estimated=10.00 -> delta=+20.00%
        # (flagged: média |Δ| 20.00% > 5.00%) -> factor = 12/10 = 1.2000
        for _ in range(3):
            self._observation(op.codigo_op, Decimal("20.00"),
                              actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                              of_operation=op)

        suggestions = services.processparameter_suggestion()

        row = next(r for r in suggestions if r["operacao"] == "OP-PP-MAP")
        self.assertEqual(row["mean_actual_hh"], Decimal("12.00"))
        self.assertEqual(row["mean_estimated_hh"], Decimal("10.00"))
        self.assertEqual(row["factor"], Decimal("1.2000"))
        self.assertEqual(row["current_value"], Decimal("40.0000"))
        self.assertEqual(row["proposed_value"], Decimal("48.0000"))

    def test_estimated_hh_medio_zero_nao_gera_proposed_value(self):
        self._observation("OP-PP-ZERO", Decimal("8.00"),
                          actual_hh=Decimal("5.00"), estimated_hh=Decimal("0.00"))
        self._observation("OP-PP-ZERO", Decimal("-9.00"),
                          actual_hh=Decimal("5.00"), estimated_hh=Decimal("0.00"))
        self._observation("OP-PP-ZERO", Decimal("7.00"),
                          actual_hh=Decimal("5.00"), estimated_hh=Decimal("0.00"))

        suggestions = services.processparameter_suggestion()

        row = next(r for r in suggestions if r["operacao"] == "OP-PP-ZERO")
        self.assertEqual(row["mean_estimated_hh"], Decimal("0.00"))
        self.assertIsNone(row["factor"])
        self.assertIsNone(row["proposed_value"])

    def test_operacao_nao_flagged_nao_aparece_na_sugestao(self):
        self._observation("OP-PP-OK", Decimal("2.00"))
        self._observation("OP-PP-OK", Decimal("-3.00"))
        self._observation("OP-PP-OK", Decimal("1.00"))
        # média |Δ| = 2.00 <= 5.00 -> 'ok', não 'review_recommended'

        suggestions = services.processparameter_suggestion()

        operacoes = [r["operacao"] for r in suggestions]
        self.assertNotIn("OP-PP-OK", operacoes)

    def test_sugestao_nao_persiste_processparameter(self):
        op = self._op_com_metodo("OP-PP-NOWRITE")
        pp = self.ProcessParameter.objects.create(
            operacao=op.codigo_op, metodo="radial", material=None, valor=Decimal("40.0000"),
            unidade="mm/min", descricao="avanço teste",
        )
        for _ in range(3):
            self._observation(op.codigo_op, Decimal("20.00"),
                              actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                              of_operation=op)

        services.processparameter_suggestion()

        pp.refresh_from_db()
        self.assertEqual(pp.valor, Decimal("40.0000"))

    def test_detail_renderiza_proposta_manual_para_operacao_flagged(self):
        op = self._op_com_metodo("OP-PP-DETAIL")
        # precisa ser o codigo_op do roteiro *desta* OF -> usa um já copiado
        of_op = OFOperation.objects.filter(item__ordem=self.of).exclude(pk=op.pk).first()
        of_op.metodo = "radial"
        of_op.save(update_fields=["metodo"])
        self.ProcessParameter.objects.create(
            operacao=of_op.codigo_op, metodo="radial", material=None, valor=Decimal("40.0000"),
            unidade="mm/min", descricao="avanço teste",
        )
        for _ in range(3):
            self._observation(of_op.codigo_op, Decimal("20.00"),
                              actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                              of_operation=of_op)
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "proposta manual")
        self.assertContains(response, "48,0000")

    def test_suggestion_computation_e_escopada_as_operacoes_informadas(self):
        # SQ-COST-8 achado 1: processparameter_suggestion() era computada para TODAS as
        # operações flagged e só depois a view descartava as de fora da OF atual. O
        # parâmetro `operacoes` permite escopar o cálculo antes, sem query desperdiçada.
        for _ in range(3):
            self._observation("OP-SCOPE-A", Decimal("20.00"),
                              actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"))
        for _ in range(3):
            self._observation("OP-SCOPE-B", Decimal("30.00"),
                              actual_hh=Decimal("13.00"), estimated_hh=Decimal("10.00"))

        todas = services.processparameter_suggestion()
        operacoes_todas = {r["operacao"] for r in todas}
        self.assertIn("OP-SCOPE-A", operacoes_todas)
        self.assertIn("OP-SCOPE-B", operacoes_todas)

        escopadas = services.processparameter_suggestion(operacoes={"OP-SCOPE-A"})
        operacoes_escopadas = {r["operacao"] for r in escopadas}
        self.assertIn("OP-SCOPE-A", operacoes_escopadas)
        self.assertNotIn("OP-SCOPE-B", operacoes_escopadas)

    def test_view_computa_sugestao_somente_para_operacoes_da_of_atual(self):
        # Integração: a operação flagged de OUTRA OF não deve aparecer no contexto da
        # view, e (por consequência do escopo acima) nem é computada para ela.
        op_desta_of = OFOperation.objects.filter(item__ordem=self.of).first()
        for _ in range(3):
            self._observation(op_desta_of.codigo_op, Decimal("20.00"),
                              actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                              of_operation=op_desta_of)
        self._observation("OP-DE-OUTRA-OF", Decimal("30.00"),
                          actual_hh=Decimal("13.00"), estimated_hh=Decimal("10.00"))
        self._observation("OP-DE-OUTRA-OF", Decimal("-31.00"),
                          actual_hh=Decimal("13.00"), estimated_hh=Decimal("10.00"))
        self._observation("OP-DE-OUTRA-OF", Decimal("29.00"),
                          actual_hh=Decimal("13.00"), estimated_hh=Decimal("10.00"))
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")

        self.assertEqual(response.status_code, 200)
        operacoes_no_contexto = {row["operacao"] for row in response.context["review_signal_flagged"]}
        self.assertIn(op_desta_of.codigo_op, operacoes_no_contexto)
        self.assertNotIn("OP-DE-OUTRA-OF", operacoes_no_contexto)

    def test_detail_renderiza_traco_para_metodo_ambiguo_mas_mantem_fator_e_medias(self):
        # SQ-COST-8 achado 5: quando as observações fechadas de uma operação divergem
        # quanto ao `metodo` do OFOperation vinculado, current_value/proposed_value
        # ficam None (services.processparameter_suggestion, branch "ambíguo") — mas
        # fator e médias continuam sendo mostrados. Faltava cobertura de template p/
        # esse branch (só havia teste de serviço).
        of_op = OFOperation.objects.filter(item__ordem=self.of).first()
        of_op.metodo = "radial"
        of_op.save(update_fields=["metodo"])
        outro_op = self._op_com_metodo(of_op.codigo_op, metodo="cnc")
        self.ProcessParameter.objects.create(
            operacao=of_op.codigo_op, metodo="radial", material=None, valor=Decimal("40.0000"),
            unidade="mm/min", descricao="avanço teste",
        )
        self._observation(of_op.codigo_op, Decimal("20.00"),
                          actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                          of_operation=of_op)
        self._observation(of_op.codigo_op, Decimal("20.00"),
                          actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                          of_operation=outro_op)
        self._observation(of_op.codigo_op, Decimal("20.00"),
                          actual_hh=Decimal("12.00"), estimated_hh=Decimal("10.00"),
                          of_operation=of_op)
        self.client.force_login(self.user)

        response = self.client.get(f"/ofs/{self.of.pk}/")
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        idx = content.index("Sinal de Revis")
        row_start = content.index(of_op.codigo_op, idx)
        row_end = content.index("</tr>", row_start)
        row_html = content[row_start:row_end]
        self.assertEqual(row_html.count("—"), 2)
        self.assertIn("1,2000×", row_html)
        self.assertIn("12,00", row_html)
        self.assertNotIn("40,0000", row_html)
        self.assertNotIn("48,0000", row_html)


class ProductionObservationAdminTests(TenantTestCase):
    """SQ-COST-4: admin somente-leitura para ProductionObservation (padrão de
    apps.integrations.sap_b1.admin.SapB1ReadOnlyAdmin: sem add/delete, todos os campos
    readonly)."""

    def setUp(self):
        from apps.production.admin import ProductionObservationAdmin
        from apps.production.models import ProductionObservation
        self.site = AdminSite()
        self.admin_obj = ProductionObservationAdmin(ProductionObservation, self.site)
        self.request = RequestFactory().get("/admin/")
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_hv_admin")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng HV Admin", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-91", crea_state="SP",
        )
        q = create_feixe_quotation(self.customer, "Feixe HV Admin")
        approve_quotation(q, self.engineer)
        of = services.convert_quotation_to_of(q, created_by=self.user)
        self.observation = ProductionObservation.objects.create(
            operacao="SOLDA-01", ordem=of,
            estimated_custo=Decimal("100.00"), actual_hh=Decimal("12.50"),
            observed_rate=Decimal("10.00"), estimated_hh=Decimal("10.00"),
            delta_horas_pct=Decimal("25.00"),
        )

    def test_admin_e_somente_leitura(self):
        self.assertFalse(self.admin_obj.has_add_permission(self.request))
        self.assertFalse(self.admin_obj.has_delete_permission(self.request, self.observation))
        readonly = self.admin_obj.get_readonly_fields(self.request, obj=self.observation)
        self.assertIn("delta_horas_pct", readonly)
        self.assertIn("estimated_hh", readonly)

    def test_admin_list_display_inclui_delta(self):
        self.assertIn("delta_horas_pct", self.admin_obj.list_display)


class ITPServiceTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="insp")
        UserProfile.objects.create(
            user=self.user, full_name="Inspetor", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-56", crea_state="SP")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_itp"), full_name="Eng",
            role="engenheiro", crea_number="CREA-55", crea_state="SP")
        self.q = create_feixe_quotation(self.customer, "Feixe ITP")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def _request(self):
        request = RequestFactory().post("/ofs/", REMOTE_ADDR="127.0.0.1")
        request.user = self.user
        return request

    def test_generate_itp_cria_plano_a_partir_do_roteiro(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        applicable_ops = OFOperation.objects.filter(item__ordem=self.of, aplicavel=True).count()
        self.assertIsInstance(plan, InspectionPlan)
        self.assertEqual(plan.ordem, self.of)
        self.assertEqual(plan.source_snapshot_hash, self.of.snapshot_hash)
        self.assertEqual(plan.source_operations_count, applicable_ops)
        self.assertEqual(plan.items.count(), applicable_ops)
        first = plan.items.order_by("sequence").first()
        first_op = OFOperation.objects.filter(item__ordem=self.of, aplicavel=True).order_by(
            "item__sort_order", "sequence", "id").first()
        self.assertEqual(first.of_operation, first_op)
        self.assertEqual(first.codigo_op, first_op.codigo_op)
        self.assertEqual(first.codigo_item, first_op.item.codigo_item)
        self.assertEqual(first.metodo, first_op.metodo)
        self.assertEqual(first.status, InspectionItem.STATUS_PENDING)

    def test_generate_itp_idempotente_nao_duplica_itens(self):
        plan1 = services.generate_inspection_plan(self.of, generated_by=self.user)
        count1 = plan1.items.count()
        plan2 = services.generate_inspection_plan(self.of, generated_by=self.user)
        self.assertEqual(plan1.pk, plan2.pk)
        self.assertEqual(plan2.items.count(), count1)

    def test_generate_itp_bloqueia_sem_operacoes_aplicaveis(self):
        OFOperation.objects.filter(item__ordem=self.of).update(aplicavel=False)
        with self.assertRaises(ValidationError):
            services.generate_inspection_plan(self.of, generated_by=self.user)

    def test_accept_inspection_item_registra_responsavel_data_e_notas(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        item = plan.items.first()
        accepted = services.accept_inspection_item(
            item, accepted_by=self.user, notes="OK dimensional")
        accepted.refresh_from_db()
        self.assertEqual(accepted.status, InspectionItem.STATUS_ACCEPTED)
        self.assertEqual(accepted.accepted_by, self.user)
        self.assertIsNotNone(accepted.accepted_at)
        self.assertEqual(accepted.notes, "OK dimensional")

    def test_accept_inspection_item_bloqueia_reaceite(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        item = plan.items.first()
        services.accept_inspection_item(item, accepted_by=self.user)
        with self.assertRaises(ValidationError):
            services.accept_inspection_item(item, accepted_by=self.user)

    def test_itp_services_gravam_access_log(self):
        plan = services.generate_inspection_plan(
            self.of, generated_by=self.user, request=self._request())
        item = plan.items.first()
        services.accept_inspection_item(item, accepted_by=self.user, request=self._request())
        self.assertTrue(AccessLog.objects.filter(action="itp_generate", resource_type="InspectionPlan").exists())
        self.assertTrue(AccessLog.objects.filter(action="itp_accept", resource_type="InspectionItem").exists())

    def test_accept_todos_itens_conclui_plano(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        for item in plan.items.all():
            services.accept_inspection_item(item, accepted_by=self.user)
        plan.refresh_from_db()
        self.assertEqual(plan.status, InspectionPlan.STATUS_COMPLETED)
        self.assertIsNotNone(plan.completed_at)

    def test_classificacao_nao_trata_cortar_como_ndt(self):
        from types import SimpleNamespace
        cortar = SimpleNamespace(codigo_op="OP-CORTAR", descricao="CORTAR CHAPA")
        recortar = SimpleNamespace(codigo_op="OP-RECORTAR", descricao="RECORTAR CHICANA")
        rt = SimpleNamespace(codigo_op="OP-RT", descricao="RT SOLDA")
        self.assertEqual(services._inspection_type_for(cortar), "dimensional")
        self.assertEqual(services._inspection_type_for(recortar), "dimensional")
        self.assertEqual(services._inspection_type_for(rt), "ndt")

    def test_constraint_bloqueia_aceito_sem_responsavel_data(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        op = OFOperation.objects.filter(item__ordem=self.of, aplicavel=True).first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InspectionItem.objects.create(
                    plan=plan,
                    of_operation=None,
                    sequence=999,
                    codigo_item=op.item.codigo_item,
                    item_descricao=op.item.descricao,
                    codigo_op="OP-INVALIDO",
                    descricao="Invalido",
                    criterio="Teste",
                    status=InspectionItem.STATUS_ACCEPTED,
                )


class ITPViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="inspv", password="x")
        UserProfile.objects.create(
            user=self.user, full_name="Insp View", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-57", crea_state="SP")
        self.orc_user = User.objects.create_user(username="orcv", password="x")
        UserProfile.objects.create(
            user=self.orc_user, full_name="Orc View", role=UserProfile.ROLE_ORCAMENTISTA)
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_itpv"), full_name="Eng",
            role="engenheiro", crea_number="CREA-56", crea_state="SP")
        self.q = create_feixe_quotation(self.customer, "Feixe ITP View")
        approve_quotation(self.q, self.engineer)
        self.of = services.convert_quotation_to_of(self.q, created_by=self.user)

    def test_generate_itp_view_cria_plano(self):
        self.client.force_login(self.user)
        resp = self.client.post(f"/ofs/{self.of.pk}/itp/gerar/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(InspectionPlan.objects.filter(ordem=self.of).exists())

    def test_accept_itp_item_view_aceita_item(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        item = plan.items.first()
        self.client.force_login(self.user)
        resp = self.client.post(
            f"/ofs/itp/{item.pk}/aceitar/",
            {"notes": "Conferido no recebimento"},
        )
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, InspectionItem.STATUS_ACCEPTED)
        self.assertEqual(item.accepted_by, self.user)

    def test_generate_itp_view_bloqueia_role_sem_permissao(self):
        self.client.force_login(self.orc_user)
        resp = self.client.post(f"/ofs/{self.of.pk}/itp/gerar/")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(InspectionPlan.objects.filter(ordem=self.of).exists())

    def test_accept_itp_item_view_bloqueia_role_sem_permissao(self):
        plan = services.generate_inspection_plan(self.of, generated_by=self.user)
        item = plan.items.first()
        self.client.force_login(self.orc_user)
        resp = self.client.post(f"/ofs/itp/{item.pk}/aceitar/", {"notes": "tentativa"})
        self.assertEqual(resp.status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.status, InspectionItem.STATUS_PENDING)


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


class HorasDecompositionTests(TenantTestCase):
    """SQ-COST-3: decomposição de horas orçadas (estimated_hh) vs reais (actual_hh)."""

    def setUp(self):
        from datetime import date
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="op_hd")
        self.engineer = UserProfile.objects.create(
            user=User.objects.create_user(username="eng_hd"), full_name="Eng",
            role="engenheiro", crea_number="CREA-10", crea_state="SP")
        self.today = date.today()

    def _of_em_producao(self, titulo):
        q = create_feixe_quotation(self.customer, titulo)
        approve_quotation(q, self.engineer)
        of = services.convert_quotation_to_of(q, created_by=self.user)
        services.liberar(of, by=self.user)
        services.iniciar_producao(of, by=self.user)
        return of

    def test_fechamento_grava_estimated_hh_do_ofoperation(self):
        """A observação de fechamento snapshota estimated_hh de OFOperation.horas_hh."""
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe HD1")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0, horas_hh__gt=0).first()
        self.assertIsNotNone(op, "Precisa de uma operação com horas_hh>0 para este teste")
        services.log_production_entry(op, self.user, Decimal("10"), Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.get(ordem=of, operacao=op.codigo_op)
        self.assertEqual(obs.estimated_hh, op.horas_hh)

    def test_delta_horas_pct_positivo_quando_real_maior_que_estimado(self):
        """actual_hh > estimated_hh -> delta_horas_pct > 0 (estourou horas)."""
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe HD2")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0, horas_hh__gt=0).first()
        self.assertIsNotNone(op)
        actual_hh = op.horas_hh * Decimal("2")  # dobro do estimado
        services.log_production_entry(op, self.user, actual_hh, Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.get(ordem=of, operacao=op.codigo_op)
        expected = ((actual_hh - op.horas_hh) / op.horas_hh * 100).quantize(Decimal("0.01"))
        self.assertEqual(obs.delta_horas_pct, expected)
        self.assertGreater(obs.delta_horas_pct, 0)

    def test_delta_horas_pct_negativo_quando_real_menor_que_estimado(self):
        """actual_hh < estimated_hh -> delta_horas_pct < 0 (folga de horas)."""
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe HD3")
        op = OFOperation.objects.filter(
            item__ordem=of, custo__gt=0, horas_hh__gt=Decimal("1")
        ).first()
        self.assertIsNotNone(op)
        actual_hh = (op.horas_hh / Decimal("2")).quantize(Decimal("0.01"))
        self.assertGreater(actual_hh, 0)
        services.log_production_entry(op, self.user, actual_hh, Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.get(ordem=of, operacao=op.codigo_op)
        expected = ((actual_hh - op.horas_hh) / op.horas_hh * 100).quantize(Decimal("0.01"))
        self.assertEqual(obs.delta_horas_pct, expected)
        self.assertLess(obs.delta_horas_pct, 0)

    def test_delta_horas_pct_none_quando_estimated_hh_zero_sem_crash(self):
        """estimated_hh=0 (op. de valor fixo) não gera div/0; delta_horas_pct fica None."""
        from decimal import Decimal
        from apps.production.models import ProductionObservation
        of = self._of_em_producao("Feixe HD4")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0).first()
        self.assertIsNotNone(op)
        # Simula operação de valor fixo: custo>0 mas sem horas estimadas.
        op.horas_hh = Decimal("0")
        op.save(update_fields=["horas_hh"])
        services.log_production_entry(op, self.user, Decimal("5"), Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.get(ordem=of, operacao=op.codigo_op)
        self.assertEqual(obs.estimated_hh, Decimal("0"))
        self.assertIsNone(obs.delta_horas_pct)

    def test_regressao_observed_rate_e_actual_rate_inalterados(self):
        """Regressão: observed_rate/ActualRate (Welford) continuam funcionando após o campo aditivo."""
        from decimal import Decimal
        from apps.production.models import ActualRate, ProductionObservation
        of = self._of_em_producao("Feixe HD5")
        op = OFOperation.objects.filter(item__ordem=of, custo__gt=0).first()
        self.assertIsNotNone(op)
        services.log_production_entry(op, self.user, Decimal("10"), Decimal("0"), self.today)
        services.concluir(of, by=self.user)
        obs = ProductionObservation.objects.get(ordem=of, operacao=op.codigo_op)
        expected_rate = (op.custo / Decimal("10")).quantize(Decimal("0.01"))
        self.assertEqual(obs.observed_rate, expected_rate)
        ar = ActualRate.objects.get(operacao=op.codigo_op)
        self.assertEqual(ar.sample_count, 1)
        self.assertAlmostEqual(float(ar.mean_rate), float(expected_rate), places=2)


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
        self.client.force_login(self.engineer.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "abc", "hours_hm": "0", "entry_date": "2026-06-23"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())

    def test_appoint_view_horas_negativas(self):
        """POST com hours_hh='-1' retorna 302 sem criar ProductionEntry."""
        from apps.production.models import ProductionEntry
        self.client.force_login(self.engineer.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "-1", "hours_hm": "0", "entry_date": "2026-06-23"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())

    def test_appoint_view_horas_acima_de_24(self):
        """POST com hours_hh='30' retorna 302 sem criar ProductionEntry (>24 bloqueado)."""
        from datetime import date
        from apps.production.models import ProductionEntry
        self.client.force_login(self.engineer.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "30", "hours_hm": "0", "entry_date": str(date.today())},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())

    def test_appoint_view_data_futura(self):
        """POST com entry_date no futuro retorna 302 sem criar ProductionEntry."""
        from datetime import date, timedelta
        from apps.production.models import ProductionEntry
        future_date = date.today() + timedelta(days=1)
        self.client.force_login(self.engineer.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "2", "hours_hm": "0", "entry_date": str(future_date)},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())

    def test_appoint_view_horas_maquina_acima_de_24(self):
        """POST com hours_hm='30' retorna 302 sem criar ProductionEntry (hm>24 bloqueado)."""
        from datetime import date
        from apps.production.models import ProductionEntry
        self.client.force_login(self.engineer.user)
        resp = self.client.post(
            f"/ofs/operacao/{self.op.pk}/apontar/",
            {"hours_hh": "2", "hours_hm": "30", "entry_date": str(date.today())},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionEntry.objects.filter(of_operation=self.op).exists())


class ApprovalStageGateTests(TenantTestCase):
    """T7: is_convertible consulta os ApprovalStage required=True do tenant.

    O estágio built-in `technical` (CREA) preserva EXATAMENTE a trava anterior ao
    F10; um estágio não-builtin obrigatório sem resolver bloqueia (Wellington Q10);
    desligar `required` desse estágio remove o gate.
    """

    def setUp(self):
        from apps.access.models import ApprovalStage  # noqa: F401 (garante app carregado)

        self.customer = Customer.objects.create(company_name="ACME")
        self.quotation = create_feixe_quotation(self.customer, "Feixe")
        self.user = User.objects.create_user(username="eng")
        self.engineer = UserProfile.objects.create(
            user=self.user, full_name="Eng PE", role="engenheiro",
            crea_number="CREA-123", crea_state="SP",
        )

    def test_technical_builtin_semeado_required_e_travado(self):
        from apps.access.models import ApprovalStage

        stage = ApprovalStage.objects.get(key="technical")
        self.assertTrue(stage.is_builtin)
        self.assertTrue(stage.required)

    def test_defaults_igual_comportamento_atual(self):
        # Sem aprovação técnica -> NÃO convertível (idêntico ao gate pré-F10)…
        self.assertFalse(services.is_convertible(self.quotation))
        # …com aprovação técnica ativa casando o snapshot -> convertível.
        approve_quotation(self.quotation, self.engineer)
        self.assertTrue(services.is_convertible(self.quotation))

    def test_estagio_nao_builtin_obrigatorio_bloqueia_e_toggle_off_libera(self):
        from apps.access.models import ApprovalStage

        approve_quotation(self.quotation, self.engineer)  # técnico satisfeito
        self.assertTrue(services.is_convertible(self.quotation))

        stage = ApprovalStage.objects.create(
            key="comercial", label="Aprovação comercial", order=20,
            required=True, is_builtin=False,
        )
        # estágio obrigatório sem resolver conhecido -> não satisfeito -> bloqueia
        self.assertFalse(services.is_convertible(self.quotation))

        # desligar `required` remove o gate desse estágio
        stage.required = False
        stage.save(update_fields=["required"])
        self.assertTrue(services.is_convertible(self.quotation))

    def test_estagio_configurado_com_capability_nao_bloqueia_em_m3(self):
        # RBAC V2 M3: um estágio do builder (com approver_capability) fica CONFIGURADO mas
        # sua execução (case/task) só chega em M4 -> não gateia ainda (evita travar a
        # conversão ao montar o fluxo). Difere do estágio cru sem capability, que bloqueia.
        from apps.access.models import ApprovalStage

        approve_quotation(self.quotation, self.engineer)  # técnico satisfeito
        ApprovalStage.objects.create(
            key="comercial-m3", label="Aprovação comercial", order=20,
            required=True, is_builtin=False, approver_capability="approval.commercial_sign",
        )
        self.assertTrue(services.is_convertible(self.quotation))

    def test_fallback_sem_estagios_semeados_exige_tecnico(self):
        """Schema legado sem estágios semeados: cai no técnico built-in sintético."""
        from apps.access.models import ApprovalStage

        ApprovalStage.objects.all().delete()
        self.assertFalse(services.is_convertible(self.quotation))
        approve_quotation(self.quotation, self.engineer)
        self.assertTrue(services.is_convertible(self.quotation))
