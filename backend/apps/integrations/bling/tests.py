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

    def test_access_token_accepts_jwt_up_to_4096_chars(self):
        """Bling JWTs can reach ~3 000 chars; max_length must accommodate them without ValidationError."""
        long_token = "a" * 3001
        config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="cid-long",
            client_secret="csec-long",
            access_token=long_token,
            refresh_token="rtk-long",
            company_id="emp-long",
        )

        config.refresh_from_db()
        self.assertEqual(config.access_token, long_token)

    def test_refresh_token_accepts_jwt_up_to_4096_chars(self):
        """Refresh tokens from Bling may also be JWTs; max_length must not truncate or reject them."""
        long_token = "r" * 3001
        config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="cid-long-rt",
            client_secret="csec-long-rt",
            access_token="atk-long-rt",
            refresh_token=long_token,
            company_id="emp-long-rt",
        )

        config.refresh_from_db()
        self.assertEqual(config.refresh_token, long_token)


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

    def test_base_url_uses_api_host(self):
        from apps.integrations.bling.client import BLING_BASE_URL

        self.assertIn(
            "api.bling.com.br",
            BLING_BASE_URL,
            "BLING_BASE_URL deve usar api.bling.com.br (host atual da API v3), não www.bling.com.br",
        )
        self.assertNotIn(
            "www.bling.com.br",
            BLING_BASE_URL,
            "BLING_BASE_URL não deve usar www.bling.com.br (host legado)",
        )

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

    def test_oauth_refresh_token_saves_new_refresh_token_when_rotated(self):
        """Provider returns a new refresh_token → it must be persisted so next refresh succeeds."""
        fake_now = timezone.now()
        token_response = {
            "access_token": "rotated-access-token",
            "refresh_token": "rotated-refresh-token",
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
        self.assertEqual(
            self.config.refresh_token,
            "rotated-refresh-token",
            "refresh_token deve ser atualizado quando o provedor rotaciona tokens",
        )

    def test_oauth_refresh_token_preserves_old_refresh_token_when_not_rotated(self):
        """Provider omits refresh_token in response → old one must be kept intact."""
        fake_now = timezone.now()
        token_response = {
            "access_token": "new-access-no-rotation",
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
        self.assertEqual(
            self.config.refresh_token,
            "old-refresh-token",
            "refresh_token original deve ser preservado quando o provedor não rotaciona",
        )

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

    def test_request_makes_single_http_attempt_on_transient_failure(self):
        import requests as req_lib
        from apps.integrations.bling.client import BlingTransientError

        call_count = 0

        def timeout_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise req_lib.Timeout("timeout simulado")

        self.bling_client._session.request = timeout_side_effect

        with self.assertRaises(BlingTransientError):
            self.bling_client._request("GET", "/test")

        self.assertEqual(
            call_count,
            1,
            "_request deve fazer exatamente 1 tentativa HTTP; retry é responsabilidade do Celery",
        )


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

    def test_export_of_for_schema_no_log_on_transient_error(self):
        from apps.integrations.bling.client import BlingTransientError
        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling_for_schema

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.side_effect = BlingTransientError("timeout")
            with self.assertRaises(BlingTransientError):
                export_of_to_bling_for_schema(self.of.pk, self.tenant.schema_name)

        self.assertFalse(
            BlingExportLog.objects.filter(of_id=self.of.pk).exists(),
            "Erros transientes não devem gerar log de erro em tentativas intermediárias",
        )

    def test_task_no_log_on_intermediate_transient_retry(self):
        from apps.integrations.bling.client import BlingTransientError
        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.side_effect = BlingTransientError("timeout")
            with self.assertRaises(Exception):
                export_of_to_bling.apply(
                    args=[self.of.pk, self.tenant.schema_name],
                    retries=0,
                    throw=True,
                )

        self.assertFalse(
            BlingExportLog.objects.filter(of_id=self.of.pk).exists(),
            "Tentativas intermediárias transientes não devem criar log de erro",
        )

    def test_task_logs_error_on_final_transient_retry_exhaustion(self):
        from apps.integrations.bling.client import BlingTransientError
        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import _TASK_MAX_RETRIES, export_of_to_bling

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.side_effect = BlingTransientError("servidor indisponivel")
            with self.assertRaises(Exception):
                export_of_to_bling.apply(
                    args=[self.of.pk, self.tenant.schema_name],
                    retries=_TASK_MAX_RETRIES,
                    throw=True,
                )

        log = BlingExportLog.objects.get(of_id=self.of.pk)
        self.assertEqual(log.status, BlingExportLog.STATUS_ERROR)
        self.assertIn("servidor indisponivel", log.error)

    def test_build_nfe_payload_uses_prefetch_cache_without_extra_query(self):
        from django.db import connection
        from django.db.models import Prefetch
        from django.test.utils import CaptureQueriesContext

        from apps.integrations.bling.tasks import _build_nfe_payload
        from apps.production.models import OFItem, OrdemFabricacao

        of = OrdemFabricacao.objects.select_related(
            "quotation__customer"
        ).prefetch_related(
            Prefetch("itens", queryset=OFItem.objects.order_by("sort_order", "codigo_item", "pk"))
        ).get(pk=self.of.pk)

        with CaptureQueriesContext(connection) as ctx:
            _build_nfe_payload(of)

        self.assertEqual(
            len(ctx.captured_queries),
            0,
            f"_build_nfe_payload deve usar o prefetch cache sem disparar queries extras; "
            f"disparou {len(ctx.captured_queries)}: {[q['sql'][:120] for q in ctx.captured_queries]}",
        )

    def test_export_of_to_bling_extracts_id_from_data_envelope(self):
        """Bling API v3 wraps responses in {'data': {...}}; bling_nfe_id must still be captured."""
        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.return_value = {"data": {"id": 99, "situacao": {"valor": 100}}}
            export_of_to_bling(self.of.pk, self.tenant.schema_name)

        log = BlingExportLog.objects.get(of_id=self.of.pk)
        self.assertEqual(log.status, BlingExportLog.STATUS_SUCCESS)
        self.assertEqual(log.bling_nfe_id, "99", "id deve ser extraído de dentro do envelope 'data'")
        self.assertIsNone(log.error)

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


class BlingClientTokenAutoRefreshTests(TenantTestCase):
    def setUp(self):
        from apps.integrations.bling.client import BlingClient

        self.config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="cid-autorefresh",
            client_secret="csec-autorefresh",
            access_token="old-token",
            refresh_token="rtk-autorefresh",
            company_id="empresa-autorefresh",
        )
        self.bling_client = BlingClient(config=self.config)

    def _make_success_response(self):
        resp = mock.MagicMock()
        resp.status_code = 200
        resp.content = b'{"id": 1}'
        resp.json.return_value = {"id": 1}
        resp.raise_for_status.return_value = None
        return resp

    def _make_401_response(self):
        import requests as req_lib

        resp = mock.MagicMock()
        resp.status_code = 401
        resp.raise_for_status.side_effect = req_lib.HTTPError("401 Unauthorized", response=resp)
        return resp

    def test_expired_token_triggers_refresh_before_request(self):
        """Token expired → oauth_refresh_token called before API request."""
        self.config.token_expires_at = timezone.now() - timedelta(seconds=30)
        self.config.save(update_fields=["token_expires_at"])

        self.bling_client._session.request = mock.MagicMock(
            return_value=self._make_success_response()
        )
        with mock.patch.object(self.bling_client, "oauth_refresh_token") as mock_refresh:
            self.bling_client.post_nfe({"numero": "001"})

        mock_refresh.assert_called_once()

    def test_valid_token_does_not_trigger_preemptive_refresh(self):
        """Token still valid → oauth_refresh_token must NOT be called preemptively."""
        self.config.token_expires_at = timezone.now() + timedelta(hours=1)
        self.config.save(update_fields=["token_expires_at"])

        self.bling_client._session.request = mock.MagicMock(
            return_value=self._make_success_response()
        )
        with mock.patch.object(self.bling_client, "oauth_refresh_token") as mock_refresh:
            self.bling_client.post_nfe({"numero": "001"})

        mock_refresh.assert_not_called()

    def test_missing_token_expiry_skips_preemptive_refresh(self):
        """No token_expires_at → oauth_refresh_token must NOT be called preemptively."""
        self.config.token_expires_at = None
        self.config.save(update_fields=["token_expires_at"])

        self.bling_client._session.request = mock.MagicMock(
            return_value=self._make_success_response()
        )
        with mock.patch.object(self.bling_client, "oauth_refresh_token") as mock_refresh:
            self.bling_client.post_nfe({"numero": "001"})

        mock_refresh.assert_not_called()

    def test_401_triggers_refresh_and_retry(self):
        """On 401, client refreshes token and retries the request exactly once."""
        call_count = 0

        def session_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._make_401_response()
            return self._make_success_response()

        self.bling_client._session.request = mock.MagicMock(side_effect=session_side_effect)
        with mock.patch.object(self.bling_client, "oauth_refresh_token") as mock_refresh:
            result = self.bling_client.post_nfe({"numero": "001"})

        self.assertEqual(call_count, 2, "Should make exactly 2 HTTP calls: original + retry")
        mock_refresh.assert_called_once()
        self.assertEqual(result, {"id": 1})

    def test_401_after_refresh_raises_client_error(self):
        """If the retry after 401+refresh also returns 401, raises BlingClientError."""
        from apps.integrations.bling.client import BlingClientError

        self.bling_client._session.request = mock.MagicMock(
            return_value=self._make_401_response()
        )
        with mock.patch.object(self.bling_client, "oauth_refresh_token"):
            with self.assertRaises(BlingClientError):
                self.bling_client.post_nfe({"numero": "001"})

    def test_oauth_endpoint_does_not_trigger_401_retry_loop(self):
        """oauth_refresh_token itself uses explicit headers → 401 on it raises immediately."""
        import requests as req_lib
        from apps.integrations.bling.client import BlingClientError

        self.bling_client._session.request = mock.MagicMock(
            return_value=self._make_401_response()
        )
        with self.assertRaises(BlingClientError) as ctx:
            self.bling_client.oauth_refresh_token(
                client_id="cid",
                client_secret="csec",
                refresh_token="rtk",
            )

        self.assertEqual(self.bling_client._session.request.call_count, 1)
        self.assertEqual(ctx.exception.status_code, 401)


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

    def test_credential_fields_are_editable_not_readonly(self):
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig
        from django.contrib import admin

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )
        credential_fields = ("client_id", "client_secret", "access_token", "refresh_token")
        for field_name in credential_fields:
            self.assertNotIn(
                field_name,
                admin_instance.readonly_fields,
                f"{field_name} deve ser editável (com máscara), não readonly",
            )

    def test_metadata_fields_are_readonly(self):
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig
        from django.contrib import admin

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )
        for field_name in ("provider", "created_at", "updated_at"):
            self.assertIn(
                field_name,
                admin_instance.readonly_fields,
                f"{field_name} deve ser readonly",
            )

    def test_credential_fields_use_password_widget_in_form(self):
        from apps.integrations.bling.admin import BlingIntegrationConfigAdmin
        from apps.integrations.bling.models import BlingIntegrationConfig
        from django.contrib import admin
        from django import forms

        admin_instance = BlingIntegrationConfigAdmin(
            BlingIntegrationConfig, admin.site
        )
        form_instance = admin_instance.form()
        credential_fields = ("client_id", "client_secret", "access_token", "refresh_token")
        for field_name in credential_fields:
            widget = form_instance.fields[field_name].widget
            self.assertIsInstance(
                widget,
                forms.PasswordInput,
                f"{field_name} deve usar PasswordInput para mascarar o segredo",
            )


class BlingIdempotencyTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        from apps.accounts.models import UserProfile
        from apps.audit.services import approve_quotation
        from apps.production import services as prod_services
        from apps.quotations.models import Customer
        from apps.quotations.services import create_feixe_quotation

        self.customer = Customer.objects.create(
            company_name="ACME Idempotency",
            cnpj="55.666.777/0001-88",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe Idempotency")
        user = User.objects.create_user(username="eng_idem")
        engineer = UserProfile.objects.create(
            user=user,
            full_name="Eng Idem",
            role="engenheiro",
            crea_number="CREA-111",
            crea_state="SP",
        )
        approve_quotation(self.quotation, engineer)
        self.of = prod_services.convert_quotation_to_of(self.quotation, created_by=user)

        self.config = BlingIntegrationConfig.objects.create(
            enabled=True,
            client_id="cid-idem",
            client_secret="csec-idem",
            access_token="atk-idem",
            refresh_token="rtk-idem",
            company_id="emp-idem",
        )

    def test_second_export_returns_existing_nfe_id_without_api_call(self):
        """Second call for the same OF must return the existing bling_nfe_id without calling the API."""
        from unittest import mock

        from apps.integrations.bling.tasks import export_of_to_bling_for_schema

        call_count = 0

        def counting_post_nfe(payload):
            nonlocal call_count
            call_count += 1
            return {"id": 42}

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.side_effect = counting_post_nfe

            result1 = export_of_to_bling_for_schema(self.of.pk, self.tenant.schema_name)
            result2 = export_of_to_bling_for_schema(self.of.pk, self.tenant.schema_name)

        self.assertEqual(call_count, 1, "API deve ser chamada apenas uma vez para a mesma OF")
        self.assertEqual(result1["bling_nfe_id"], "42")
        self.assertEqual(result2["bling_nfe_id"], "42")
        self.assertEqual(result2["status"], "success")

    def test_second_export_does_not_create_second_success_log(self):
        """Exportar a mesma OF duas vezes não deve criar dois BlingExportLog de sucesso."""
        from unittest import mock

        from apps.integrations.bling.models import BlingExportLog
        from apps.integrations.bling.tasks import export_of_to_bling_for_schema

        with mock.patch("apps.integrations.bling.tasks.BlingClient") as MockClient:
            MockClient.return_value.post_nfe.return_value = {"id": 55}

            export_of_to_bling_for_schema(self.of.pk, self.tenant.schema_name)
            export_of_to_bling_for_schema(self.of.pk, self.tenant.schema_name)

        logs = BlingExportLog.objects.filter(
            of_id=self.of.pk, status=BlingExportLog.STATUS_SUCCESS
        )
        self.assertEqual(logs.count(), 1, "Deve existir apenas um log de sucesso para a OF")

    def test_unique_constraint_prevents_duplicate_success_logs(self):
        """Constraint de banco: criar dois logs de sucesso para a mesma OF lança IntegrityError."""
        from django.db import IntegrityError

        from apps.integrations.bling.models import BlingExportLog

        BlingExportLog.objects.create(
            of_id=self.of.pk,
            status=BlingExportLog.STATUS_SUCCESS,
            bling_nfe_id="100",
        )

        with self.assertRaises(IntegrityError):
            BlingExportLog.objects.create(
                of_id=self.of.pk,
                status=BlingExportLog.STATUS_SUCCESS,
                bling_nfe_id="200",
            )

    def test_multiple_error_logs_allowed_for_same_of(self):
        """Múltiplos logs de erro para a mesma OF devem ser permitidos (apenas sucesso é único)."""
        from apps.integrations.bling.models import BlingExportLog

        BlingExportLog.objects.create(
            of_id=self.of.pk,
            status=BlingExportLog.STATUS_ERROR,
            error="Erro 1",
        )
        BlingExportLog.objects.create(
            of_id=self.of.pk,
            status=BlingExportLog.STATUS_ERROR,
            error="Erro 2",
        )

        self.assertEqual(
            BlingExportLog.objects.filter(
                of_id=self.of.pk, status=BlingExportLog.STATUS_ERROR
            ).count(),
            2,
            "Múltiplos logs de erro para a mesma OF devem ser permitidos",
        )
