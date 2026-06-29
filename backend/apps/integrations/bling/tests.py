from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.integrations.bling.models import BlingIntegrationConfig


class BlingInitModuleTests(TenantTestCase):
    def test_default_app_config_not_defined(self):
        import apps.integrations.bling as bling_module
        self.assertFalse(
            hasattr(bling_module, "default_app_config"),
            "default_app_config é código morto no Django 4.1+ e deve ser removido",
        )


class BlingIntegrationConfigTests(TenantTestCase):
    def test_config_create_and_retrieve(self):
        config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="my-client-id",
            client_secret="my-client-secret",
            access_token="access-tok-123",
            refresh_token="refresh-tok-456",
            company_id="empresa-001",
        )

        fetched = BlingIntegrationConfig.objects.get(pk=config.pk)

        self.assertEqual(fetched.enabled, True)
        self.assertEqual(fetched.client_id, "my-client-id")
        self.assertEqual(fetched.client_secret, "my-client-secret")
        self.assertEqual(fetched.access_token, "access-tok-123")
        self.assertEqual(fetched.refresh_token, "refresh-tok-456")
        self.assertIsNone(fetched.token_expires_at)
        self.assertEqual(fetched.company_id, "empresa-001")

    def test_encrypted_fields_are_not_stored_in_plaintext(self):
        config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="super-secret-client-id",
            client_secret="super-secret-client-secret",
            access_token="super-secret-access-token",
            refresh_token="super-secret-refresh-token",
            company_id="emp-002",
        )

        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT client_id, client_secret, access_token, refresh_token "
                "FROM integrations_bling_blingintegrationconfig WHERE id = %s",
                [config.pk],
            )
            row = cursor.fetchone()

        self.assertNotEqual(row[0], "super-secret-client-id")
        self.assertNotEqual(row[1], "super-secret-client-secret")
        self.assertNotEqual(row[2], "super-secret-access-token")
        self.assertNotEqual(row[3], "super-secret-refresh-token")

    def test_singleton_config_is_enforced(self):
        BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="id1",
            client_secret="sec1",
            access_token="tok1",
            refresh_token="ref1",
            company_id="emp-1",
        )

        with self.assertRaisesMessage(ValidationError, "apenas uma configuracao Bling"):
            BlingIntegrationConfig.objects.create(
                enabled=False,
                client_id="id2",
                client_secret="sec2",
                access_token="tok2",
                refresh_token="ref2",
                company_id="emp-2",
            )

    def test_provider_field_is_always_bling(self):
        config = BlingIntegrationConfig.objects.create(
            enabled=False,
            client_id="cid",
            client_secret="csec",
            access_token="atk",
            refresh_token="rtk",
            company_id="emp",
        )

        self.assertEqual(config.provider, "bling")


class BlingClientTests(TenantTestCase):
    def setUp(self):
        from apps.integrations.bling.client import BlingClient

        self.config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="client-id-test",
            client_secret="client-secret-test",
            access_token="old-access-token",
            refresh_token="old-refresh-token",
            company_id="empresa-test",
        )
        self.bling_client = BlingClient(config=self.config)

    def test_oauth_refresh_token_updates_access_token_and_expires_at(self):
        fake_now = timezone.now()
        token_response = {
            "access_token": "new-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with mock.patch.object(self.bling_client, "_request", return_value=token_response):
            with mock.patch("apps.integrations.bling.client.timezone") as mock_tz:
                mock_tz.now.return_value = fake_now
                self.bling_client.oauth_refresh_token(
                    client_id="client-id-test",
                    client_secret="client-secret-test",
                    refresh_token="old-refresh-token",
                )

        self.config.refresh_from_db()
        self.assertEqual(self.config.access_token, "new-access-token")
        expected_expires = fake_now + timedelta(seconds=3600)
        self.assertEqual(self.config.token_expires_at, expected_expires)

    def test_get_headers_returns_bearer_token(self):
        self.config.access_token = "my-bearer-token"
        self.config.save(update_fields=["access_token"])

        headers = self.bling_client.get_headers()

        self.assertEqual(headers["Authorization"], "Bearer my-bearer-token")
        self.assertIn("Content-Type", headers)

    def test_post_nfe_calls_correct_endpoint(self):
        payload = {"numero": "001", "serie": "1"}
        expected_response = {"id": 42, "situacao": {"valor": 100}}
        with mock.patch.object(self.bling_client, "_request", return_value=expected_response) as mock_req:
            result = self.bling_client.post_nfe(payload)

        mock_req.assert_called_once_with("POST", "/nfe", json=payload)
        self.assertEqual(result, expected_response)

    def test_get_nfe_status_calls_correct_endpoint(self):
        nfe_id = "12345"
        expected_response = {"id": 12345, "situacao": {"valor": 101}}
        with mock.patch.object(self.bling_client, "_request", return_value=expected_response) as mock_req:
            result = self.bling_client.get_nfe_status(nfe_id)

        mock_req.assert_called_once_with("GET", f"/nfe/{nfe_id}")
        self.assertEqual(result, expected_response)


class BlingExportLogTests(TenantTestCase):
    def test_export_log_success_creates_and_retrieves(self):
        from apps.integrations.bling.models import BlingExportLog

        log = BlingExportLog.objects.create(
            of_id=1,
            status=BlingExportLog.STATUS_SUCCESS,
            bling_nfe_id="42",
        )
        fetched = BlingExportLog.objects.get(pk=log.pk)

        self.assertEqual(fetched.of_id, 1)
        self.assertEqual(fetched.status, BlingExportLog.STATUS_SUCCESS)
        self.assertEqual(fetched.bling_nfe_id, "42")
        self.assertIsNone(fetched.error)
        self.assertIsNotNone(fetched.created_at)

    def test_export_log_error_stores_message(self):
        from apps.integrations.bling.models import BlingExportLog

        log = BlingExportLog.objects.create(
            of_id=99,
            status=BlingExportLog.STATUS_ERROR,
            error="API falhou com status 500",
        )
        fetched = BlingExportLog.objects.get(pk=log.pk)

        self.assertEqual(fetched.status, BlingExportLog.STATUS_ERROR)
        self.assertEqual(fetched.error, "API falhou com status 500")
        self.assertFalse(fetched.bling_nfe_id)


class BlingExportTaskTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        from apps.accounts.models import UserProfile
        from apps.audit.services import approve_quotation
        from apps.production import services as prod_services
        from apps.quotations.models import Customer
        from apps.quotations.services import create_feixe_quotation

        self.customer = Customer.objects.create(
            company_name="ACME Caldeiraria",
            cnpj="12.345.678/0001-99",
            email="fiscal@acme.com",
            city="Sao Paulo",
            state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe Bling")
        user = User.objects.create_user(username="eng_bling_task")
        engineer = UserProfile.objects.create(
            user=user,
            full_name="Eng Bling",
            role="engenheiro",
            crea_number="CREA-999",
            crea_state="SP",
        )
        approve_quotation(self.quotation, engineer)
        self.of = prod_services.convert_quotation_to_of(self.quotation, created_by=user)

        self.config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="cid-task",
            client_secret="csec-task",
            access_token="atk-task",
            refresh_token="rtk-task",
            company_id="emp-task",
        )

    def test_export_of_to_bling_creates_success_log(self):
        from unittest import mock

        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.return_value = {"id": 77, "situacao": {"valor": 100}}
            export_of_to_bling(self.of.pk, self.tenant.schema_name)

        log = BlingExportLog.objects.get(of_id=self.of.pk)
        self.assertEqual(log.status, BlingExportLog.STATUS_SUCCESS)
        self.assertEqual(log.bling_nfe_id, "77")
        self.assertIsNone(log.error)

    def test_export_of_to_bling_uses_schema_context(self):
        from unittest import mock

        from django_tenants.utils import schema_context

        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling

        with mock.patch(
            "apps.integrations.bling.tasks.schema_context", wraps=schema_context
        ) as mock_ctx:
            with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
                MockClient.return_value.post_nfe.return_value = {"id": 88}
                export_of_to_bling(self.of.pk, self.tenant.schema_name)

        mock_ctx.assert_called_once_with(self.tenant.schema_name)
        self.assertTrue(BlingExportLog.objects.filter(of_id=self.of.pk).exists())

    def test_export_of_to_bling_creates_error_log_on_client_failure(self):
        from unittest import mock

        from apps.integrations.bling.client import BlingClientError
        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.side_effect = BlingClientError(
                "Servidor indisponivel", status_code=503
            )
            with self.assertRaises(Exception):
                export_of_to_bling(self.of.pk, self.tenant.schema_name)

        log = BlingExportLog.objects.get(of_id=self.of.pk)
        self.assertEqual(log.status, BlingExportLog.STATUS_ERROR)
        self.assertIn("Servidor indisponivel", log.error)

    def test_export_of_to_bling_builds_payload_with_of_number_and_cnpj(self):
        from unittest import mock

        from apps.integrations.bling.tasks import export_of_to_bling

        captured_payload = {}

        def capture_post_nfe(payload):
            captured_payload.update(payload)
            return {"id": 55}

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.side_effect = capture_post_nfe
            export_of_to_bling(self.of.pk, self.tenant.schema_name)

        self.assertIn("numero", captured_payload)
        self.assertEqual(captured_payload["numero"], self.of.number)
        self.assertIn("contato", captured_payload)
        self.assertEqual(captured_payload["contato"]["cpfCnpj"], "12.345.678/0001-99")
        self.assertIn("itens", captured_payload)
        self.assertIsInstance(captured_payload["itens"], list)
        self.assertGreater(len(captured_payload["itens"]), 0)


class BlingAdminActionTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        from apps.accounts.models import UserProfile
        from apps.audit.services import approve_quotation
        from apps.production import services as prod_services
        from apps.quotations.models import Customer
        from apps.quotations.services import create_feixe_quotation

        self.customer = Customer.objects.create(
            company_name="ACME Admin",
            cnpj="11.222.333/0001-44",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe Admin Bling")
        user = User.objects.create_user(username="eng_bling_admin")
        engineer = UserProfile.objects.create(
            user=user,
            full_name="Eng Admin",
            role="engenheiro",
            crea_number="CREA-777",
            crea_state="SP",
        )
        approve_quotation(self.quotation, engineer)
        self.of = prod_services.convert_quotation_to_of(self.quotation, created_by=user)
        self.user = user

    def test_admin_action_export_to_bling_dispatches_task(self):
        from unittest import mock

        from django.contrib import admin
        from django.test import RequestFactory

        from apps.production.admin import OrdemFabricacaoAdmin
        from apps.production.models import OrdemFabricacao

        request = RequestFactory().post("/admin/")
        request.user = self.user

        admin_instance = OrdemFabricacaoAdmin(OrdemFabricacao, admin.site)

        with mock.patch(
            "apps.production.admin.export_of_to_bling_task"
        ) as mock_task:
            with mock.patch.object(admin_instance, "message_user"):
                admin_instance.export_to_bling(
                    request, OrdemFabricacao.objects.filter(pk=self.of.pk)
                )

        mock_task.delay.assert_called_once_with(self.of.pk, mock.ANY)


class BlingFakeClientTests(TenantTestCase):
    def setUp(self):
        from apps.integrations.bling.client import BlingFakeClient

        self.config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="fake-client-id",
            client_secret="fake-client-secret",
            access_token="fake-access-token",
            refresh_token="fake-refresh-token",
            company_id="empresa-fake",
        )
        self.fake_client = BlingFakeClient(config=self.config)

    def test_fake_oauth_refresh_updates_config(self):
        self.fake_client.oauth_refresh_token(
            client_id="fake-client-id",
            client_secret="fake-client-secret",
            refresh_token="fake-refresh-token",
        )

        self.config.refresh_from_db()
        self.assertIsNotNone(self.config.access_token)
        self.assertIsNotNone(self.config.token_expires_at)

    def test_fake_get_headers_returns_bearer(self):
        headers = self.fake_client.get_headers()

        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_fake_post_nfe_returns_dict(self):
        payload = {"numero": "001"}
        result = self.fake_client.post_nfe(payload)

        self.assertIsInstance(result, dict)
        self.assertIn("id", result)

    def test_fake_get_nfe_status_returns_dict(self):
        result = self.fake_client.get_nfe_status("999")

        self.assertIsInstance(result, dict)
        self.assertIn("id", result)


class BlingHealthCheckAdminTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import RequestFactory

        self.config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="health-check-client-id",
            client_secret="health-check-client-secret",
            access_token="health-check-access-token",
            refresh_token="health-check-refresh-token",
            company_id="empresa-health",
        )
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@test.com",
            password="admin-pass",
        )
        self.factory = RequestFactory()

    def test_check_health_action_exists_on_admin(self):
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig
        from django.contrib import admin

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )
        self.assertTrue(
            hasattr(admin_instance, "check_health"),
            "check_health action should exist on admin"
        )
        self.assertIn(
            "check_health",
            admin_instance.actions,
            "check_health should be in available actions",
        )

    def test_check_health_success_with_fake_client(self):
        from unittest import mock

        from django.contrib import admin
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig

        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = {}

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )

        with mock.patch(
            "apps.integrations.bling.admin.BlingClient"
        ) as MockClient:
            MockClient.return_value.ping.return_value = {}
            with mock.patch.object(admin_instance, "message_user") as mock_message:
                admin_instance.check_health(
                    request,
                    BlingIntegrationConfig.objects.filter(pk=self.config.pk),
                )

            mock_message.assert_called()
            call_args = mock_message.call_args
            self.assertIn("sucesso", call_args[0][1].lower())

    def test_check_health_failure_with_fake_client(self):
        from unittest import mock

        from django.contrib import admin
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig
        from apps.integrations.bling.client import BlingClientError

        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = {}

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )

        with mock.patch(
            "apps.integrations.bling.admin.BlingClient"
        ) as MockClient:
            MockClient.return_value.ping.side_effect = BlingClientError(
                "Servidor indisponível", status_code=503
            )
            with mock.patch.object(admin_instance, "message_user") as mock_message:
                admin_instance.check_health(
                    request,
                    BlingIntegrationConfig.objects.filter(pk=self.config.pk),
                )

            mock_message.assert_called()
            call_args = mock_message.call_args
            self.assertIn("erro", call_args[0][1].lower())

    def test_check_health_displays_fields_readonly(self):
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig
        from django.contrib import admin

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )
        self.assertIn(
            "client_id",
            admin_instance.readonly_fields,
            "client_id should be read-only",
        )
        self.assertIn(
            "client_secret",
            admin_instance.readonly_fields,
            "client_secret should be read-only",
        )
        self.assertIn(
            "access_token",
            admin_instance.readonly_fields,
            "access_token should be read-only",
        )
        self.assertIn(
            "refresh_token",
            admin_instance.readonly_fields,
            "refresh_token should be read-only",
        )
