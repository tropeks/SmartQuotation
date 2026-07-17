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
