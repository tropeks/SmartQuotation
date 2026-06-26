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
    SapB1IntegrationConfig,
    SapB1SyncAttempt,
    SapB1SyncBinding,
    SapB1SyncRun,
)
from apps.integrations.sap_b1 import services
from apps.integrations.sap_b1.tasks import process_sap_b1_sync_run
from apps.integrations.sap_b1 import views
from apps.production import services as production_services
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


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
