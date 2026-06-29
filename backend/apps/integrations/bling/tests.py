from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.integrations.bling.models import BlingIntegrationConfig


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
