from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from apps.integrations.omie.admin import OmieFiscalDocumentAdmin, OmieInvoiceAttemptAdmin, OmieInvoiceRunAdmin
from apps.accounts.models import UserProfile
from apps.audit.services import approve_quotation
from apps.integrations.omie.client import HttpOmiePermanentError, HttpOmieTransientError
from apps.integrations.omie.fake import MemoryOmieClient
from apps.integrations.omie.models import (
    OmieFiscalDocument,
    OmieIntegrationConfig,
    OmieInvoiceAttempt,
    OmieInvoiceRun,
)
from apps.integrations.omie import services
from apps.integrations.omie.tasks import process_omie_invoice_run
from apps.production import services as production_services
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class OmieServicesTests(TenantTestCase):
    def setUp(self):
        self.client = MemoryOmieClient()
        self.customer = Customer.objects.create(
            company_name="ACME",
            cnpj="12.345.678/0001-00",
            email="fiscal@acme.com",
            city="Sao Paulo",
            state="SP",
        )
        self.user = User.objects.create_user(username="eng_omie")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng Omie",
            role="engenheiro",
            crea_number="CREA-991",
            crea_state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe Omie")
        approve_quotation(self.quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(self.quotation, created_by=self.user)
        production_services.liberar(self.of, by=self.user)
        production_services.iniciar_producao(self.of, by=self.user)
        with mock.patch("apps.production.services._schedule_omie_nfe_issue"):
            production_services.concluir(self.of, by=self.user)
        self.config = OmieIntegrationConfig.objects.create(
            enabled=True,
            app_key="key",
            app_secret="secret",
            company_code="01",
            environment="sandbox",
            fiscal_defaults={"base_url": "https://omie.example/api", "cfop": "5101"},
        )

    def test_serialize_nfe_from_of_is_deterministic(self):
        payload1 = services.serialize_nfe_from_of(self.of, self.config)
        payload2 = services.serialize_nfe_from_of(self.of, self.config)

        self.assertEqual(payload1, payload2)
        self.assertEqual(payload1["document_number"], self.of.number)
        self.assertEqual(payload1["customer"]["cnpj"], "12.345.678/0001-00")

    def test_maybe_enqueue_nfe_issue_is_idempotent(self):
        run1 = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")
        run2 = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")

        self.assertIsNotNone(run1)
        self.assertEqual(run1.pk, run2.pk)
        self.assertEqual(OmieFiscalDocument.objects.count(), 1)
        self.assertEqual(OmieInvoiceRun.objects.count(), 1)

    def test_process_invoice_run_marks_document_issued(self):
        run = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")

        services.process_invoice_run(run, client=self.client)

        run.refresh_from_db()
        run.document.refresh_from_db()
        self.assertEqual(run.status, OmieInvoiceRun.STATUS_SUCCESS)
        self.assertEqual(run.document.status, OmieFiscalDocument.STATUS_ISSUED)
        self.assertTrue(run.document.remote_document_id)
        self.assertEqual(run.attempts.count(), 1)

    def test_process_invoice_run_uses_run_idempotency_key_remotely(self):
        run = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")
        client = mock.Mock()
        client.issue_nfe.return_value = {
            "remote_document_id": "omie-123",
            "remote_number": "NFE-123",
            "status": "issued",
        }

        services.process_invoice_run(run, client=client)

        client.issue_nfe.assert_called_once_with(run.payload, idempotency_key=run.idempotency_key)

    def test_issued_document_is_not_rebuilt_after_success(self):
        run = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")
        services.process_invoice_run(run, client=self.client)

        document = OmieFiscalDocument.objects.get(of=self.of)
        original_payload = document.payload
        original_snapshot = document.source_snapshot
        original_defaults = document.fiscal_defaults_snapshot
        original_config_id = document.config_id

        self.of.title = "Feixe Omie Alterado"
        self.of.save(update_fields=["title"])
        self.config.fiscal_defaults["cfop"] = "6101"
        self.config.save(update_fields=["fiscal_defaults", "updated_at"])

        rebuilt = services.maybe_enqueue_nfe_issue(self.of, trigger="admin")

        document.refresh_from_db()
        self.assertEqual(rebuilt.pk, run.pk)
        self.assertEqual(document.payload, original_payload)
        self.assertEqual(document.source_snapshot, original_snapshot)
        self.assertEqual(document.fiscal_defaults_snapshot, original_defaults)
        self.assertEqual(document.config_id, original_config_id)

    def test_process_invoice_run_persists_failed_attempt(self):
        class FailingClient(MemoryOmieClient):
            def issue_nfe(self, payload, *, idempotency_key=""):
                raise HttpOmieTransientError("Omie indisponivel")

        run = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")

        with self.assertRaises(HttpOmieTransientError):
            services.process_invoice_run(run, client=FailingClient())

        run.refresh_from_db()
        run.document.refresh_from_db()
        self.assertEqual(run.status, OmieInvoiceRun.STATUS_FAILED)
        self.assertEqual(run.document.status, OmieFiscalDocument.STATUS_FAILED)
        self.assertEqual(OmieInvoiceAttempt.objects.filter(run=run).count(), 1)

    def test_process_invoice_run_rejects_non_issued_remote_status(self):
        class PendingClient(MemoryOmieClient):
            def issue_nfe(self, payload, *, idempotency_key=""):
                response = super().issue_nfe(payload, idempotency_key=idempotency_key)
                response["status"] = "processing"
                return response

        run = services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed")

        with self.assertRaisesMessage(HttpOmiePermanentError, "non-issued status"):
            services.process_invoice_run(run, client=PendingClient())

        run.refresh_from_db()
        run.document.refresh_from_db()
        self.assertEqual(run.status, OmieInvoiceRun.STATUS_FAILED)
        self.assertEqual(run.document.status, OmieFiscalDocument.STATUS_FAILED)

    def test_manual_trigger_bypasses_emit_on_of_completed_flag(self):
        self.config.emit_on_of_completed = False
        self.config.save(update_fields=["emit_on_of_completed", "updated_at"])

        self.assertIsNone(services.maybe_enqueue_nfe_issue(self.of, trigger="of_completed"))

        run = services.maybe_enqueue_nfe_issue(self.of, trigger="admin")

        self.assertIsNotNone(run)
        self.assertEqual(run.trigger, "admin")

    def test_singleton_config_is_enforced(self):
        with self.assertRaisesMessage(ValidationError, "apenas uma configuracao Omie"):
            OmieIntegrationConfig.objects.create(
                enabled=False,
                app_key="key-2",
                app_secret="secret-2",
                company_code="02",
                environment="prod",
                fiscal_defaults={"base_url": "https://omie-2.example/api"},
            )

    def test_run_healthcheck_returns_operational_summary(self):
        summary = services.run_healthcheck(client=self.client)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["remote"]["status"], "ok")


class OmieTasksTests(TenantTestCase):
    def setUp(self):
        self.client = MemoryOmieClient()
        customer = Customer.objects.create(
            company_name="ACME",
            cnpj="12.345.678/0001-00",
            city="Sao Paulo",
            state="SP",
        )
        user = User.objects.create_user(username="eng_omie_task")
        engineer = UserProfile.objects.create(
            user=user,
            full_name="Eng Omie Task",
            role="engenheiro",
            crea_number="CREA-992",
            crea_state="SP",
        )
        quotation = create_feixe_quotation(customer, "Feixe Omie Task")
        approve_quotation(quotation, engineer)
        of = production_services.convert_quotation_to_of(quotation, created_by=user)
        production_services.liberar(of, by=user)
        production_services.iniciar_producao(of, by=user)
        with mock.patch("apps.production.services._schedule_omie_nfe_issue"):
            production_services.concluir(of, by=user)
        self.config = OmieIntegrationConfig.objects.create(
            enabled=True,
            app_key="key",
            app_secret="secret",
            company_code="01",
            environment="sandbox",
            fiscal_defaults={"base_url": "https://omie.example/api"},
        )
        self.run = services.maybe_enqueue_nfe_issue(of, trigger="of_completed")

    @mock.patch("apps.integrations.omie.services.build_omie_client")
    def test_process_invoice_run_task_uses_tenant_schema(self, build_client):
        build_client.return_value = self.client

        result = process_omie_invoice_run(schema_name=self.tenant.schema_name, run_id=self.run.pk)

        self.assertEqual(result["run_id"], self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, OmieInvoiceRun.STATUS_SUCCESS)

    def test_process_invoice_run_task_marks_run_skipped_when_disabled(self):
        self.config.enabled = False
        self.config.save(update_fields=["enabled", "updated_at"])

        result = process_omie_invoice_run(schema_name=self.tenant.schema_name, run_id=self.run.pk)

        self.assertEqual(result["status"], OmieInvoiceRun.STATUS_SKIPPED)
        self.run.refresh_from_db()
        document = self.run.document
        document.refresh_from_db()
        self.assertEqual(self.run.status, OmieInvoiceRun.STATUS_SKIPPED)
        self.assertEqual(document.status, OmieFiscalDocument.STATUS_READY)
        self.assertEqual(self.run.error_message, "Omie integration is disabled")

    @mock.patch("apps.integrations.omie.tasks.process_invoice_run.delay", side_effect=RuntimeError("broker down"))
    def test_enqueue_invoice_run_async_marks_run_failed_when_publish_fails(self, _delay):
        ok = services.enqueue_invoice_run_async(self.run, schema_name=self.tenant.schema_name)

        self.assertFalse(ok)
        self.run.refresh_from_db()
        document = self.run.document
        document.refresh_from_db()
        self.assertEqual(self.run.status, OmieInvoiceRun.STATUS_FAILED)
        self.assertEqual(document.status, OmieFiscalDocument.STATUS_READY)
        self.assertIn("Failed to enqueue Omie invoice run", self.run.error_message)


class OmieAdminTests(TenantTestCase):
    def setUp(self):
        self.site = AdminSite()
        self.request = RequestFactory().get("/admin/")
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_omie_admin")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng Omie Admin",
            role="engenheiro",
            crea_number="CREA-993",
            crea_state="SP",
        )
        quotation = create_feixe_quotation(self.customer, "Feixe Omie Admin")
        approve_quotation(quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(quotation, created_by=self.user)
        production_services.liberar(self.of, by=self.user)
        production_services.iniciar_producao(self.of, by=self.user)
        with mock.patch("apps.production.services._schedule_omie_nfe_issue"):
            production_services.concluir(self.of, by=self.user)
        self.config = OmieIntegrationConfig.objects.create(
            enabled=True,
            app_key="key",
            app_secret="secret",
            company_code="01",
            environment="sandbox",
            fiscal_defaults={"base_url": "https://omie.example/api"},
        )
        self.run = services.maybe_enqueue_nfe_issue(self.of, trigger="admin")
        services.process_invoice_run(self.run, client=MemoryOmieClient())
        self.document = OmieFiscalDocument.objects.get(of=self.of)
        self.attempt = self.run.attempts.first()

    def test_document_admin_is_read_only(self):
        admin_obj = OmieFiscalDocumentAdmin(OmieFiscalDocument, self.site)

        readonly = admin_obj.get_readonly_fields(self.request, obj=self.document)

        self.assertIn("payload", readonly)
        self.assertIn("status", readonly)
        self.assertFalse(admin_obj.has_add_permission(self.request))
        self.assertFalse(admin_obj.has_delete_permission(self.request, self.document))

    def test_run_admin_is_read_only(self):
        admin_obj = OmieInvoiceRunAdmin(OmieInvoiceRun, self.site)

        readonly = admin_obj.get_readonly_fields(self.request, obj=self.run)

        self.assertIn("payload", readonly)
        self.assertIn("status", readonly)
        self.assertFalse(admin_obj.has_add_permission(self.request))
        self.assertFalse(admin_obj.has_delete_permission(self.request, self.run))

    def test_attempt_admin_is_read_only(self):
        admin_obj = OmieInvoiceAttemptAdmin(OmieInvoiceAttempt, self.site)

        readonly = admin_obj.get_readonly_fields(self.request, obj=self.attempt)

        self.assertIn("request_payload", readonly)
        self.assertIn("status", readonly)
        self.assertFalse(admin_obj.has_add_permission(self.request))
        self.assertFalse(admin_obj.has_delete_permission(self.request, self.attempt))


class OmieAdminHealthViewTests(TenantTestCase):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.user = User.objects.create_superuser(username="admin_omie", email="admin@example.com", password="secret123456")
        with schema_context(self.tenant.schema_name):
            OmieIntegrationConfig.objects.create(
                enabled=True,
                app_key="key",
                app_secret="secret",
                company_code="01",
                environment="sandbox",
                fiscal_defaults={"base_url": "https://omie.example/api"},
            )

    @mock.patch("apps.integrations.omie.views.services.run_healthcheck")
    def test_admin_healthcheck_requires_auth(self, run_healthcheck):
        response = self.client.get("/admin/omie/health/")

        self.assertEqual(response.status_code, 302)
        run_healthcheck.assert_not_called()

    @mock.patch("apps.integrations.omie.views.services.run_healthcheck")
    def test_admin_healthcheck_returns_json_for_staff(self, run_healthcheck):
        run_healthcheck.return_value = {"ok": True, "remote": {"status": "ok"}}
        self.client.force_login(self.user)

        response = self.client.get("/admin/omie/health/")

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True, "remote": {"status": "ok"}})

    @mock.patch("apps.integrations.omie.views.services.run_healthcheck")
    def test_admin_healthcheck_returns_503_on_failure(self, run_healthcheck):
        run_healthcheck.return_value = {"enabled": True, "ok": False, "remote": {"status": "error"}}
        self.client.force_login(self.user)

        response = self.client.get("/admin/omie/health/")

        self.assertEqual(response.status_code, 503)
