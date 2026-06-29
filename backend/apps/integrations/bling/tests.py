from django.core.exceptions import ValidationError
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
