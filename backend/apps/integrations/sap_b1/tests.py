from unittest import mock

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context

from apps.accounts.models import UserProfile
from apps.audit.services import approve_quotation
from apps.integrations.sap_b1.admin import SapB1SyncAttemptAdmin, SapB1SyncRunAdmin
from apps.integrations.sap_b1.client import HttpSapB1Client, HttpSapB1PermanentError, HttpSapB1TransientError
from apps.integrations.sap_b1.fake import MemorySapB1Client
from apps.integrations.sap_b1.models import (
    SapB1ExportLog,
    SapB1IntegrationConfig,
    SapB1SyncAttempt,
    SapB1SyncBinding,
    SapB1SyncRun,
)
from apps.integrations.sap_b1 import services
from apps.integrations.sap_b1.tasks import (
    check_pending_sap_b1_exports,
    check_sap_b1_export_status,
    process_sap_b1_sync_run,
)
from apps.integrations.sap_b1 import views
from apps.production import services as production_services
from apps.production.models import OrdemFabricacao, STATUS_CONCLUIDA, STATUS_EM_PRODUCAO
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class SapB1ResponseRemoteCodeTests(SimpleTestCase):
    """Unit tests for _response_remote_code() — the function that extracts the SAP remote PK."""

    def test_extracts_doc_entry_integer_from_sap_service_layer_post_response(self):
        """Real SAP B1 POST /Orders returns DocEntry as integer; must be the remote code."""
        response = {"DocEntry": 12345, "DocNum": 67890}
        payload = {"order_number": "OF-001", "document_number": "OF-001"}

        result = services._response_remote_code(response, payload)

        self.assertEqual(str(result), "12345")

    def test_doc_entry_takes_precedence_over_order_number_fallback(self):
        """DocEntry must win over order_number/document_number payload fallbacks."""
        response = {"DocEntry": 99}
        payload = {"order_number": "OF-999", "document_number": "OF-999"}

        result = services._response_remote_code(response, payload)

        self.assertNotEqual(str(result), "OF-999")
        self.assertEqual(str(result), "99")

    def test_doc_entry_wins_over_doc_num(self):
        """DocEntry (primary key) must be preferred over DocNum (sequence number)."""
        response = {"DocEntry": 5, "DocNum": 100}
        payload = {}

        result = services._response_remote_code(response, payload)

        self.assertEqual(str(result), "5")

    def test_falls_back_to_remote_code_when_no_doc_entry(self):
        """Fake/test clients return remote_code; that still works without DocEntry."""
        response = {"remote_code": "fallback-123"}
        payload = {"order_number": "OF-001"}

        result = services._response_remote_code(response, payload)

        self.assertEqual(result, "fallback-123")

    def test_falls_back_to_order_number_when_response_empty(self):
        """Empty response (e.g. 204 on PATCH) falls back to payload order_number."""
        response = {}
        payload = {"order_number": "OF-001", "sap_doc_entry": "12345"}

        result = services._response_remote_code(response, payload)

        self.assertEqual(result, "12345")


class SapB1HttpClientTests(SimpleTestCase):
    def test_http_client_targets_service_layer_endpoints(self):
        session = mock.Mock()
        login_response = mock.Mock()
        login_response.content = b"{}"
        login_response.json.return_value = {}
        login_response.raise_for_status.return_value = None
        orders_response = mock.Mock()
        orders_response.content = b"{}"
        orders_response.json.return_value = {}
        orders_response.raise_for_status.return_value = None
        session.request.side_effect = [login_response, orders_response]

        client = HttpSapB1Client(
            base_url="https://sapb1.example",
            username="manager",
            password="secret",
            company_db="SBODEMO",
            session=session,
        )

        client.upsert_sales_order({"DocNum": "1"})

        first_call = session.request.call_args_list[0]
        second_call = session.request.call_args_list[1]
        self.assertEqual(first_call.kwargs["url"], "https://sapb1.example/b1s/v2/Login")
        self.assertEqual(
            first_call.kwargs["json"],
            {"CompanyDB": "SBODEMO", "UserName": "manager", "Password": "secret"},
        )
        self.assertEqual(second_call.kwargs["url"], "https://sapb1.example/b1s/v2/Orders")

    def test_http_client_updates_existing_sales_order_when_binding_is_present(self):
        session = mock.Mock()
        response = mock.Mock()
        response.content = b"{}"
        response.json.return_value = {}
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = HttpSapB1Client(base_url="https://sapb1.example", session=session)
        client._authenticated = True

        client.upsert_sales_order({"document_number": "OF-1", "sap_doc_entry": "12345"})

        session.request.assert_called_once()
        self.assertEqual(session.request.call_args.kwargs["method"], "PATCH")
        self.assertEqual(session.request.call_args.kwargs["url"], "https://sapb1.example/b1s/v2/Orders(12345)")


    def test_get_sales_order_status_targets_orders_endpoint(self):
        """get_sales_order_status must hit GET /Orders({entry}), not /ProductionOrders.
        The Service Layer returns DocumentStatus (OData enum), not the legacy DocStatus."""
        session = mock.Mock()
        response = mock.Mock()
        response.content = b'{"DocumentStatus": "bost_Open"}'
        response.json.return_value = {"DocumentStatus": "bost_Open"}
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = HttpSapB1Client(base_url="https://sapb1.example", session=session)
        client._authenticated = True

        result = client.get_sales_order_status("12345")

        session.request.assert_called_once()
        call_url = session.request.call_args.kwargs["url"]
        self.assertIn("/Orders(12345)", call_url)
        self.assertNotIn("ProductionOrders", call_url)
        self.assertEqual(result["DocumentStatus"], "bost_Open")


class SapB1ServicesTests(TenantTestCase):
    def setUp(self):
        self.client = MemorySapB1Client()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_sap")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng SAP",
            role="engenheiro",
            crea_number="CREA-900",
            crea_state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe SAP B1")
        approve_quotation(self.quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(self.quotation, created_by=self.user)
        production_services.liberar(self.of, by=self.user)
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )

    def test_serialize_sales_order_from_of_is_deterministic(self):
        payload1 = services.serialize_sales_order_from_of(self.of)
        payload2 = services.serialize_sales_order_from_of(self.of)

        self.assertEqual(payload1, payload2)
        self.assertEqual(payload1["document_number"], self.of.number)
        self.assertEqual(payload1["items"], payload2["items"])

    def test_serialize_bom_from_of_orders_nested_entities_explicitly(self):
        payload = services.serialize_bom_from_of(self.of)

        self.assertEqual(payload["order_number"], self.of.number)
        self.assertTrue(payload["items"])
        first_item = payload["items"][0]
        self.assertIsInstance(first_item["materials"], list)
        self.assertIsInstance(first_item["operations"], list)

    def test_enqueue_sales_order_is_idempotent(self):
        run1, created1 = services.enqueue_sales_order_sync(self.of, trigger="manual")
        run2, created2 = services.enqueue_sales_order_sync(self.of, trigger="manual")

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(run1.pk, run2.pk)
        self.assertEqual(SapB1SyncRun.objects.count(), 1)

    def test_process_sales_order_run_creates_binding_and_attempt(self):
        run, _ = services.enqueue_sales_order_sync(self.of)

        services.process_sync_run(run, self.client)

        run.refresh_from_db()
        self.assertEqual(run.status, SapB1SyncRun.STATUS_SUCCESS)
        self.assertEqual(run.remote_code, self.of.number)
        self.assertEqual(SapB1SyncAttempt.objects.filter(run=run).count(), 1)
        self.assertTrue(
            SapB1SyncBinding.objects.filter(
                entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
                local_model="production.OrdemFabricacao",
                local_id=str(self.of.pk),
                remote_code=self.of.number,
            ).exists()
        )

    def test_enqueue_sales_order_keeps_binding_remote_code_out_of_stored_payload(self):
        SapB1SyncBinding.objects.create(
            provider=SapB1IntegrationConfig.PROVIDER,
            entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
            local_model="production.OrdemFabricacao",
            local_id=str(self.of.pk),
            remote_code="12345",
            payload_hash="old-hash",
            last_direction=SapB1SyncBinding.DIRECTION_PUSH,
            source_of_truth=SapB1SyncBinding.SOURCE_LOCAL,
        )
        self.of.status = STATUS_CONCLUIDA

        run, _ = services.enqueue_sales_order_sync(self.of, trigger="auto_export")

        self.assertNotIn("sap_doc_entry", run.payload)

    def test_enqueue_sales_order_does_not_mutate_successful_run_payload_when_binding_appears(self):
        original_run, _ = services.enqueue_sales_order_sync(self.of, trigger="manual")
        original_payload = dict(original_run.payload)
        original_payload_hash = original_run.payload_hash
        original_run.status = SapB1SyncRun.STATUS_SUCCESS
        original_run.save(update_fields=["status"])

        SapB1SyncBinding.objects.create(
            provider=SapB1IntegrationConfig.PROVIDER,
            entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
            local_model="production.OrdemFabricacao",
            local_id=str(self.of.pk),
            remote_code="12345",
            payload_hash=original_payload_hash,
            last_direction=SapB1SyncBinding.DIRECTION_PUSH,
            source_of_truth=SapB1SyncBinding.SOURCE_LOCAL,
        )

        run, created = services.enqueue_sales_order_sync(self.of, trigger="auto_export")

        self.assertFalse(created)
        self.assertEqual(run.pk, original_run.pk)
        self.assertEqual(run.payload, original_payload)
        self.assertEqual(run.payload_hash, original_payload_hash)
        self.assertNotIn("sap_doc_entry", run.payload)

    def test_process_sales_order_run_uses_binding_remote_code_when_present(self):
        SapB1SyncBinding.objects.create(
            provider=SapB1IntegrationConfig.PROVIDER,
            entity_type=SapB1SyncBinding.ENTITY_SALES_ORDER,
            local_model="production.OrdemFabricacao",
            local_id=str(self.of.pk),
            remote_code="12345",
            payload_hash="old-hash",
            last_direction=SapB1SyncBinding.DIRECTION_PUSH,
            source_of_truth=SapB1SyncBinding.SOURCE_LOCAL,
        )
        run, _ = services.enqueue_sales_order_sync(self.of, trigger="auto_export")

        services.process_sync_run(run, self.client)

        self.assertIn("12345", self.client.sales_orders)
        self.assertEqual(self.client.sales_orders["12345"]["sap_doc_entry"], "12345")

    def test_process_bom_run_creates_binding(self):
        run, _ = services.enqueue_bom_sync(self.of)

        services.process_sync_run(run, self.client)

        self.assertTrue(
            SapB1SyncBinding.objects.filter(
                entity_type=SapB1SyncBinding.ENTITY_BOM,
                local_model="production.OrdemFabricacao",
                local_id=str(self.of.pk),
            ).exists()
        )

    def test_process_sync_run_persists_failed_attempt(self):
        class FailingClient(MemorySapB1Client):
            def upsert_sales_order(self, payload):
                raise HttpSapB1TransientError("SAP B1 indisponivel")

        run, _ = services.enqueue_sales_order_sync(self.of)

        with self.assertRaises(HttpSapB1TransientError):
            services.process_sync_run(run, client=FailingClient())

        run.refresh_from_db()
        self.assertEqual(run.status, SapB1SyncRun.STATUS_FAILED)
        self.assertEqual(SapB1SyncAttempt.objects.filter(run=run).count(), 1)

    def test_process_sync_run_persists_permanent_failure(self):
        class BadClient(MemorySapB1Client):
            def upsert_sales_order(self, payload):
                raise HttpSapB1PermanentError("bad payload")

        run, _ = services.enqueue_sales_order_sync(self.of)

        with self.assertRaises(HttpSapB1PermanentError):
            services.process_sync_run(run, client=BadClient())

        run.refresh_from_db()
        self.assertEqual(run.status, SapB1SyncRun.STATUS_FAILED)

    def test_disabled_path_skips_enqueue(self):
        self.config.enabled = False
        self.config.save(update_fields=["enabled", "updated_at"])

        self.assertIsNone(services.maybe_enqueue_sales_order_sync(self.of, trigger="admin"))
        self.assertIsNone(services.maybe_enqueue_bom_sync(self.of, trigger="admin"))

    def test_open_work_order_is_not_enqueued(self):
        customer = Customer.objects.create(company_name="ACME 2")
        quotation = create_feixe_quotation(customer, "Feixe SAP B1 Aberta")
        approve_quotation(quotation, self.engineer)
        open_of = production_services.convert_quotation_to_of(quotation, created_by=self.user)

        self.assertEqual(open_of.status, "aberta")
        self.assertIsNone(services.maybe_enqueue_sales_order_sync(open_of, trigger="admin"))
        self.assertIsNone(services.maybe_enqueue_bom_sync(open_of, trigger="admin"))

    def test_run_healthcheck_returns_operational_summary(self):
        summary = services.run_healthcheck(client=self.client)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["remote"]["status"], "ok")


class SapB1TasksTests(TenantTestCase):
    def setUp(self):
        self.client = MemorySapB1Client()
        customer = Customer.objects.create(company_name="ACME")
        user = User.objects.create_user(username="eng_sap_task")
        engineer = UserProfile.objects.create(
            user=user,
            full_name="Eng SAP Task",
            role="engenheiro",
            crea_number="CREA-901",
            crea_state="SP",
        )
        quotation = create_feixe_quotation(customer, "Feixe SAP B1 Task")
        approve_quotation(quotation, engineer)
        self.of = production_services.convert_quotation_to_of(quotation, created_by=user)
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )
        self.run, _ = services.enqueue_sales_order_sync(self.of)

    @mock.patch("apps.integrations.sap_b1.services.build_sap_b1_client")
    def test_process_sync_run_task_uses_tenant_schema(self, build_client):
        build_client.return_value = self.client

        result = process_sap_b1_sync_run(schema_name=self.tenant.schema_name, run_id=self.run.pk)

        self.assertEqual(result["run_id"], self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, SapB1SyncRun.STATUS_SUCCESS)

    def test_process_sync_run_task_marks_skipped_when_disabled(self):
        self.config.enabled = False
        self.config.save(update_fields=["enabled", "updated_at"])

        result = process_sap_b1_sync_run(schema_name=self.tenant.schema_name, run_id=self.run.pk)

        self.assertEqual(result["status"], SapB1SyncRun.STATUS_SKIPPED)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, SapB1SyncRun.STATUS_SKIPPED)

    @mock.patch("apps.integrations.sap_b1.tasks.process_sap_b1_sync_run.delay", side_effect=RuntimeError("broker down"))
    def test_enqueue_sync_run_async_marks_failed_when_publish_fails(self, _delay):
        ok = services.enqueue_sync_run_async(self.run, schema_name=self.tenant.schema_name)

        self.assertFalse(ok)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, SapB1SyncRun.STATUS_FAILED)
        self.assertIn("Failed to enqueue SAP B1 sync run", self.run.error_message)

    def test_successful_run_cannot_be_reset_for_requeue(self):
        services.process_sync_run(self.run, client=self.client)
        self.run.refresh_from_db()

        self.assertFalse(services.reset_sync_run_for_requeue(self.run))

    def test_process_sync_run_reprocesses_run_stuck_in_processing(self):
        self.run.status = SapB1SyncRun.STATUS_PROCESSING
        self.run.save(update_fields=["status"])

        services.process_sync_run(self.run, client=self.client)

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, SapB1SyncRun.STATUS_SUCCESS)
        self.assertTrue(SapB1SyncAttempt.objects.filter(run=self.run).exists())

    def test_reset_sync_run_for_requeue_recovers_processing_run(self):
        self.run.status = SapB1SyncRun.STATUS_PROCESSING
        self.run.save(update_fields=["status"])

        result = services.reset_sync_run_for_requeue(self.run)

        self.assertTrue(result)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, SapB1SyncRun.STATUS_PENDING)
        self.assertEqual(self.run.error_message, "")
        self.assertIsNone(self.run.finished_at)
        self.assertIn("requeued_at", self.run.result_payload)


class SapB1AdminTests(TenantTestCase):
    def setUp(self):
        self.site = AdminSite()
        self.request = RequestFactory().get("/admin/")
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_sap_admin")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng SAP Admin",
            role="engenheiro",
            crea_number="CREA-902",
            crea_state="SP",
        )
        quotation = create_feixe_quotation(self.customer, "Feixe SAP B1 Admin")
        approve_quotation(quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(quotation, created_by=self.user)
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )
        self.run, _ = services.enqueue_sales_order_sync(self.of)
        services.process_sync_run(self.run, client=MemorySapB1Client())
        self.attempt = self.run.attempts.first()

    def test_run_admin_is_read_only(self):
        admin_obj = SapB1SyncRunAdmin(SapB1SyncRun, self.site)

        readonly = admin_obj.get_readonly_fields(self.request, obj=self.run)

        self.assertIn("payload", readonly)
        self.assertIn("status", readonly)
        self.assertFalse(admin_obj.has_add_permission(self.request))
        self.assertFalse(admin_obj.has_delete_permission(self.request, self.run))

    def test_attempt_admin_is_read_only(self):
        admin_obj = SapB1SyncAttemptAdmin(SapB1SyncAttempt, self.site)

        readonly = admin_obj.get_readonly_fields(self.request, obj=self.attempt)

        self.assertIn("request_payload", readonly)
        self.assertIn("status", readonly)
        self.assertFalse(admin_obj.has_add_permission(self.request))
        self.assertFalse(admin_obj.has_delete_permission(self.request, self.attempt))


class SapB1AdminHealthViewTests(TenantTestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.user = User.objects.create_superuser(username="admin_sap", email="admin@example.com", password="secret123456")
        with schema_context(self.tenant.schema_name):
            SapB1IntegrationConfig.objects.create(
                enabled=True,
                base_url="https://sapb1.example/api",
                company_db="SBODEMO",
                username="manager",
                password="secret",
            )

    @mock.patch("apps.integrations.sap_b1.views.services.run_healthcheck")
    def test_admin_healthcheck_requires_auth(self, run_healthcheck):
        request = self.request_factory.get("/admin/sap-b1/health/")
        request.user = AnonymousUser()
        response = admin.site.admin_view(views.admin_healthcheck)(request)

        self.assertEqual(response.status_code, 302)
        run_healthcheck.assert_not_called()

    @mock.patch("apps.integrations.sap_b1.views.services.run_healthcheck")
    def test_admin_healthcheck_returns_json_for_staff(self, run_healthcheck):
        run_healthcheck.return_value = {"ok": True, "remote": {"status": "ok"}}
        request = self.request_factory.get("/admin/sap-b1/health/")
        request.user = self.user
        response = admin.site.admin_view(views.admin_healthcheck)(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True, "remote": {"status": "ok"}})

    @mock.patch("apps.integrations.sap_b1.views.services.run_healthcheck")
    def test_admin_healthcheck_returns_503_on_failure(self, run_healthcheck):
        run_healthcheck.return_value = {"enabled": True, "ok": False, "remote": {"status": "error"}}
        request = self.request_factory.get("/admin/sap-b1/health/")
        request.user = self.user
        response = admin.site.admin_view(views.admin_healthcheck)(request)

        self.assertEqual(response.status_code, 503)


class SapB1AutoExportSignalTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME Signal SAP")
        self.user = User.objects.create_user(username="eng_signal_sap")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng Signal SAP",
            role="engenheiro",
            crea_number="CREA-960",
            crea_state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe SAP B1 Signal")
        approve_quotation(self.quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(self.quotation, created_by=self.user)
        production_services.liberar(self.of, by=self.user)
        production_services.iniciar_producao(self.of, by=self.user)
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            auto_export=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )

    @mock.patch("apps.integrations.sap_b1.services._dispatch_export_of_task")
    def test_signal_enqueues_export_when_of_concluida_and_auto_export_enabled(self, mock_dispatch):
        with self.captureOnCommitCallbacks(execute=True):
            production_services.concluir(self.of, by=self.user)

        mock_dispatch.assert_called_once_with(self.of.pk, self.tenant.schema_name)

    @mock.patch("apps.integrations.sap_b1.services._dispatch_export_of_task")
    def test_signal_does_not_enqueue_when_auto_export_false(self, mock_dispatch):
        self.config.auto_export = False
        self.config.save(update_fields=["auto_export", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            production_services.concluir(self.of, by=self.user)

        mock_dispatch.assert_not_called()

    @mock.patch("apps.integrations.sap_b1.services._dispatch_export_of_task")
    def test_signal_does_not_enqueue_when_integration_disabled(self, mock_dispatch):
        self.config.enabled = False
        self.config.save(update_fields=["enabled", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            production_services.concluir(self.of, by=self.user)

        mock_dispatch.assert_not_called()

    @mock.patch("apps.integrations.sap_b1.services._dispatch_export_of_task")
    def test_idempotency_already_exported_of_not_re_exported(self, mock_dispatch):
        # Simulate: OF in CONCLUIDA with existing SUCCESS auto-export run
        self.of.status = STATUS_CONCLUIDA
        run, _ = services.enqueue_sales_order_sync(self.of, trigger="auto_export")
        run.status = SapB1SyncRun.STATUS_SUCCESS
        run.save(update_fields=["status"])

        # Simulate signal firing for CONCLUIDA transition
        self.of._pre_save_status = STATUS_EM_PRODUCAO
        with self.captureOnCommitCallbacks(execute=True):
            services._on_of_post_save(
                sender=OrdemFabricacao,
                instance=self.of,
                created=False,
            )

        mock_dispatch.assert_not_called()

    @mock.patch("apps.integrations.sap_b1.services._dispatch_export_of_task")
    def test_signal_does_not_fire_on_save_without_status_change(self, mock_dispatch):
        # Transition to CONCLUIDA then save again (no status change)
        production_services.concluir(self.of, by=self.user)
        self.of.refresh_from_db()
        mock_dispatch.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            self.of.save(update_fields=["updated_at"])

        mock_dispatch.assert_not_called()


class SapB1ExportStatusTaskTests(TenantTestCase):
    def setUp(self):
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )
        self.log = SapB1ExportLog.objects.create(
            sap_doc_entry="12345",
            sap_status=SapB1ExportLog.SAP_STATUS_PENDING,
        )

    @mock.patch("apps.integrations.sap_b1.tasks.build_sap_b1_client")
    def test_check_export_status_marks_synced_when_released(self, mock_build_client):
        """Service Layer returns DocumentStatus=bost_Close when an order is closed/released."""
        mock_client = mock.Mock()
        mock_client.get_sales_order_status.return_value = {"DocumentStatus": "bost_Close"}
        mock_build_client.return_value = mock_client

        check_sap_b1_export_status(log_id=self.log.pk, tenant_schema=self.tenant.schema_name)

        self.log.refresh_from_db()
        self.assertEqual(self.log.sap_status, SapB1ExportLog.SAP_STATUS_SYNCED)
        self.assertIsNotNone(self.log.last_checked_at)

    @mock.patch("apps.integrations.sap_b1.tasks.build_sap_b1_client")
    def test_check_export_status_updates_last_checked_on_non_released(self, mock_build_client):
        """Service Layer returns DocumentStatus=bost_Open when an order is still open."""
        mock_client = mock.Mock()
        mock_client.get_sales_order_status.return_value = {"DocumentStatus": "bost_Open"}
        mock_build_client.return_value = mock_client

        check_sap_b1_export_status(log_id=self.log.pk, tenant_schema=self.tenant.schema_name)

        self.log.refresh_from_db()
        self.assertEqual(self.log.sap_status, SapB1ExportLog.SAP_STATUS_PENDING)
        self.assertIsNotNone(self.log.last_checked_at)

    @mock.patch("apps.integrations.sap_b1.tasks.build_sap_b1_client")
    def test_check_export_status_stays_pending_when_old_docstatus_key_present(self, mock_build_client):
        """Old DI API key DocStatus=R must NOT be treated as released (wrong key)."""
        mock_client = mock.Mock()
        mock_client.get_sales_order_status.return_value = {"DocStatus": "R"}
        mock_build_client.return_value = mock_client

        check_sap_b1_export_status(log_id=self.log.pk, tenant_schema=self.tenant.schema_name)

        self.log.refresh_from_db()
        self.assertEqual(self.log.sap_status, SapB1ExportLog.SAP_STATUS_PENDING)

    @mock.patch("apps.integrations.sap_b1.tasks.build_sap_b1_client")
    def test_check_export_status_retries_on_transient_error(self, mock_build_client):
        mock_client = mock.Mock()
        mock_client.get_sales_order_status.side_effect = HttpSapB1TransientError("timeout")
        mock_build_client.return_value = mock_client

        with self.assertRaises(HttpSapB1TransientError):
            check_sap_b1_export_status(log_id=self.log.pk, tenant_schema=self.tenant.schema_name)

        self.log.refresh_from_db()
        self.assertEqual(self.log.sap_status, SapB1ExportLog.SAP_STATUS_PENDING)

    @mock.patch("apps.integrations.sap_b1.tasks.build_sap_b1_client")
    def test_check_export_status_marks_error_on_permanent_failure(self, mock_build_client):
        from apps.integrations.sap_b1.client import HttpSapB1PermanentError
        mock_client = mock.Mock()
        mock_client.get_sales_order_status.side_effect = HttpSapB1PermanentError("bad doc")
        mock_build_client.return_value = mock_client

        check_sap_b1_export_status(log_id=self.log.pk, tenant_schema=self.tenant.schema_name)

        self.log.refresh_from_db()
        self.assertEqual(self.log.sap_status, SapB1ExportLog.SAP_STATUS_ERROR)
        self.assertIn("bad doc", self.log.error_message)

    @mock.patch("apps.integrations.sap_b1.tasks.check_sap_b1_export_status.delay")
    def test_check_pending_exports_dispatches_for_pending_logs(self, mock_delay):
        result = check_pending_sap_b1_exports()

        mock_delay.assert_called_once_with(
            log_id=self.log.pk,
            tenant_schema=self.tenant.schema_name,
        )
        self.assertEqual(result["dispatched"], 1)

    @mock.patch("apps.integrations.sap_b1.tasks.check_sap_b1_export_status.delay")
    def test_check_pending_exports_skips_synced_logs(self, mock_delay):
        self.log.sap_status = SapB1ExportLog.SAP_STATUS_SYNCED
        self.log.save(update_fields=["sap_status"])

        result = check_pending_sap_b1_exports()

        mock_delay.assert_not_called()
        self.assertEqual(result["dispatched"], 0)

    @mock.patch("apps.integrations.sap_b1.tasks.check_sap_b1_export_status.delay")
    def test_check_pending_exports_skips_disabled_integration(self, mock_delay):
        self.config.enabled = False
        self.config.save(update_fields=["enabled", "updated_at"])

        check_pending_sap_b1_exports()

        mock_delay.assert_not_called()


class SapB1ConflictDetectionTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="ACME Conflict SAP")
        self.user = User.objects.create_user(username="eng_conflict_sap")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng Conflict SAP",
            role="engenheiro",
            crea_number="CREA-970",
            crea_state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe SAP B1 Conflict")
        approve_quotation(self.quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(self.quotation, created_by=self.user)
        production_services.liberar(self.of, by=self.user)
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )
        # Simulate the OF having been exported: create a successful sync run + export log
        self.run, _ = services.enqueue_sales_order_sync(self.of, trigger="auto_export")
        self.run.status = SapB1SyncRun.STATUS_SUCCESS
        self.run.save(update_fields=["status"])
        self.export_log = SapB1ExportLog.objects.create(
            sync_run=self.run,
            sap_doc_entry="DOC-CONFLICT-001",
            sap_status=SapB1ExportLog.SAP_STATUS_SYNCED,
        )

    def test_detect_conflict_when_status_changes_after_export(self):
        """Changing OF status in memory after export marks conflict on export log."""
        from apps.production.models import STATUS_EM_PRODUCAO

        self.of.status = STATUS_EM_PRODUCAO  # differs from exported status (liberada)
        services._detect_and_flag_of_conflict(self.of)

        self.export_log.refresh_from_db()
        self.assertTrue(self.export_log.conflict)
        self.assertIn("status", self.export_log.conflict_reason)

    def test_detect_conflict_when_critical_fields_change(self):
        """Editing customer_name, title, scope, or totals after export marks conflict."""
        self.of.customer_name = "New Customer Name"
        self.of.title = "New Title"
        self.of.scope = "New Scope"
        self.of.number = "OF-999"
        self.of.custo_total = self.of.custo_total + 100
        
        services._detect_and_flag_of_conflict(self.of)
        
        self.export_log.refresh_from_db()
        self.assertTrue(self.export_log.conflict)
        self.assertIn("customer_name", self.export_log.conflict_reason)
        self.assertIn("title", self.export_log.conflict_reason)
        self.assertIn("scope", self.export_log.conflict_reason)
        self.assertIn("number", self.export_log.conflict_reason)
        self.assertIn("custo_total", self.export_log.conflict_reason)

    def test_no_conflict_when_status_unchanged(self):
        """No conflict flagged when critical fields did not change after export."""
        # of.status is still STATUS_LIBERADA, same as when it was exported
        services._detect_and_flag_of_conflict(self.of)

        self.export_log.refresh_from_db()
        self.assertFalse(self.export_log.conflict)
        self.assertEqual(self.export_log.conflict_reason, "")

    def test_no_conflict_when_export_log_absent(self):
        """No action when a successful sync run exists but has no export log."""
        self.export_log.delete()

        services._detect_and_flag_of_conflict(self.of)

        self.assertFalse(SapB1ExportLog.objects.filter(conflict=True).exists())

    def test_no_conflict_when_of_never_exported(self):
        """No conflict when OF has no successful sync runs."""
        quotation2 = create_feixe_quotation(self.customer, "Feixe No Export Conflict")
        approve_quotation(quotation2, self.engineer)
        of2 = production_services.convert_quotation_to_of(quotation2, created_by=self.user)

        services._detect_and_flag_of_conflict(of2)

        self.assertFalse(SapB1ExportLog.objects.filter(conflict=True).exists())

    def test_already_conflicted_log_not_overwritten(self):
        """If export log is already conflict=True, skip re-detection (preserves original reason)."""
        self.export_log.conflict = True
        self.export_log.conflict_reason = "original reason"
        self.export_log.save(update_fields=["conflict", "conflict_reason", "updated_at"])

        self.of.status = "em_producao"
        services._detect_and_flag_of_conflict(self.of)

        self.export_log.refresh_from_db()
        self.assertEqual(self.export_log.conflict_reason, "original reason")

    def test_detect_conflict_ignores_later_bom_run_without_export_log(self):
        """A later successful BOM sync run must not shadow the sales_order export log lookup."""
        bom_run, _ = services.enqueue_bom_sync(self.of, trigger="manual")
        bom_run.status = SapB1SyncRun.STATUS_SUCCESS
        bom_run.save(update_fields=["status"])
        self.assertGreaterEqual(bom_run.started_at, self.run.started_at)

        from apps.production.models import STATUS_EM_PRODUCAO

        self.of.status = STATUS_EM_PRODUCAO  # differs from exported status (liberada)
        services._detect_and_flag_of_conflict(self.of)

        self.export_log.refresh_from_db()
        self.assertTrue(self.export_log.conflict)
        self.assertIn("status", self.export_log.conflict_reason)

    def test_signal_detects_conflict_when_exported_of_is_saved_with_changed_status(self):
        """Saving an exported OF with a different status triggers conflict via post_save signal."""
        from apps.production.models import STATUS_CANCELADA

        self.of.status = STATUS_CANCELADA
        self.of.save(update_fields=["status", "updated_at"])

        self.export_log.refresh_from_db()
        self.assertTrue(self.export_log.conflict)

    def test_force_resync_clears_conflict_flag(self):
        """force_resync admin action clears conflict and conflict_reason on export log."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from apps.integrations.sap_b1.admin import SapB1ExportLogAdmin

        self.export_log.conflict = True
        self.export_log.conflict_reason = "status changed after export"
        self.export_log.save(update_fields=["conflict", "conflict_reason", "updated_at"])

        site = AdminSite()
        admin_obj = SapB1ExportLogAdmin(SapB1ExportLog, site)
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin_conflict", "c@d.com", "pass")
        request.session = mock.Mock()
        request._messages = FallbackStorage(request)

        with mock.patch("apps.integrations.sap_b1.tasks.check_sap_b1_export_status.delay"):
            queryset = SapB1ExportLog.objects.filter(pk=self.export_log.pk)
            admin_obj.force_resync(request, queryset)

        self.export_log.refresh_from_db()
        self.assertFalse(self.export_log.conflict)
        self.assertEqual(self.export_log.conflict_reason, "")


class SapB1ExportLogAdminTests(TenantTestCase):
    def setUp(self):
        from apps.integrations.sap_b1.admin import SapB1ExportLogAdmin
        self.site = AdminSite()
        self.admin_obj = SapB1ExportLogAdmin(SapB1ExportLog, self.site)
        self.request = RequestFactory().get("/admin/")
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )
        self.log = SapB1ExportLog.objects.create(
            sap_doc_entry="12345",
            sap_status=SapB1ExportLog.SAP_STATUS_ERROR,
            error_message="previous error",
        )

    @mock.patch("apps.integrations.sap_b1.tasks.check_sap_b1_export_status.delay")
    def test_force_resync_resets_status_and_dispatches_task(self, mock_delay):
        from django.contrib.messages.storage.fallback import FallbackStorage
        self.request.user = User.objects.create_superuser("admin_export", "a@b.com", "pass")
        self.request.session = mock.Mock()
        self.request._messages = FallbackStorage(self.request)

        queryset = SapB1ExportLog.objects.filter(pk=self.log.pk)
        self.admin_obj.force_resync(self.request, queryset)

        self.log.refresh_from_db()
        self.assertEqual(self.log.sap_status, SapB1ExportLog.SAP_STATUS_PENDING)
        self.assertEqual(self.log.error_message, "")
        mock_delay.assert_called_once()


class SapB1ExportLogCreationTests(TenantTestCase):
    """Verify that export_of_to_sap_b1 and process_sync_run create SapB1ExportLog."""

    def setUp(self):
        customer = Customer.objects.create(company_name="ACME Export Log")
        user = User.objects.create_user(username="eng_export_log")
        engineer = UserProfile.objects.create(
            user=user,
            full_name="Eng Export Log",
            role="engenheiro",
            crea_number="CREA-985",
            crea_state="SP",
        )
        quotation = create_feixe_quotation(customer, "Feixe Export Log")
        approve_quotation(quotation, engineer)
        self.of = production_services.convert_quotation_to_of(quotation, created_by=user)
        production_services.liberar(self.of, by=user)
        self.config = SapB1IntegrationConfig.objects.create(
            enabled=True,
            auto_export=True,
            base_url="https://sapb1.example/api",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )

    def test_process_sales_order_run_creates_export_log(self):
        """process_sync_run creates SapB1ExportLog for successful ENTITY_SALES_ORDER runs."""
        run, _ = services.enqueue_sales_order_sync(self.of)

        services.process_sync_run(run, MemorySapB1Client())

        run.refresh_from_db()
        self.assertEqual(run.status, SapB1SyncRun.STATUS_SUCCESS)
        log = SapB1ExportLog.objects.filter(sync_run=run).first()
        self.assertIsNotNone(log, "SapB1ExportLog deve ser criado após sync de sales order bem-sucedido")
        self.assertEqual(log.sap_doc_entry, run.remote_code)
        self.assertEqual(log.sap_status, SapB1ExportLog.SAP_STATUS_PENDING)

    def test_process_bom_run_does_not_create_export_log(self):
        """process_sync_run does NOT create SapB1ExportLog for BOM runs."""
        run, _ = services.enqueue_bom_sync(self.of)

        services.process_sync_run(run, MemorySapB1Client())

        self.assertFalse(
            SapB1ExportLog.objects.filter(sync_run=run).exists(),
            "BOM runs não devem gerar SapB1ExportLog",
        )

    @mock.patch("apps.integrations.sap_b1.services.build_sap_b1_client")
    def test_export_of_to_sap_b1_creates_export_log(self, build_client):
        """export_of_to_sap_b1 task creates SapB1ExportLog linked to the run."""
        from apps.integrations.sap_b1.tasks import export_of_to_sap_b1
        build_client.return_value = MemorySapB1Client()

        export_of_to_sap_b1(schema_name=self.tenant.schema_name, of_id=self.of.pk)

        run = SapB1SyncRun.objects.filter(
            local_model="production.OrdemFabricacao",
            local_id=str(self.of.pk),
            status=SapB1SyncRun.STATUS_SUCCESS,
        ).first()
        self.assertIsNotNone(run, "SapB1SyncRun deve existir e estar SUCCESS")
        log = SapB1ExportLog.objects.filter(sync_run=run).first()
        self.assertIsNotNone(log, "SapB1ExportLog deve ser criado pela task export_of_to_sap_b1")
        self.assertEqual(log.sap_doc_entry, run.remote_code)
        self.assertEqual(log.sap_status, SapB1ExportLog.SAP_STATUS_PENDING)

    @mock.patch("apps.integrations.sap_b1.services.build_sap_b1_client")
    def test_export_of_to_sap_b1_export_log_is_idempotent(self, build_client):
        """Re-running export_of_to_sap_b1 with the same payload does not create duplicate logs."""
        from apps.integrations.sap_b1.tasks import export_of_to_sap_b1
        build_client.return_value = MemorySapB1Client()

        export_of_to_sap_b1(schema_name=self.tenant.schema_name, of_id=self.of.pk)
        export_of_to_sap_b1(schema_name=self.tenant.schema_name, of_id=self.of.pk)

        self.assertEqual(
            SapB1ExportLog.objects.filter(
                sync_run__local_model="production.OrdemFabricacao",
                sync_run__local_id=str(self.of.pk),
            ).count(),
            1,
            "Não deve haver logs duplicados após dois exports do mesmo OF",
        )

    def test_process_sync_run_stores_doc_entry_not_of_number_when_sap_returns_doc_entry(self):
        """When real SAP returns DocEntry, it must be stored — not the OF number fallback."""
        class SapStyleClient(MemorySapB1Client):
            def upsert_sales_order(self, payload):
                return {"DocEntry": 12345, "DocNum": 67890}

        run, _ = services.enqueue_sales_order_sync(self.of)
        services.process_sync_run(run, SapStyleClient())

        run.refresh_from_db()
        self.assertEqual(run.status, SapB1SyncRun.STATUS_SUCCESS)
        self.assertEqual(str(run.remote_code), "12345")
        self.assertNotEqual(run.remote_code, self.of.number)

        log = SapB1ExportLog.objects.filter(sync_run=run).first()
        self.assertIsNotNone(log)
        self.assertEqual(str(log.sap_doc_entry), "12345")
        self.assertNotEqual(log.sap_doc_entry, self.of.number)
