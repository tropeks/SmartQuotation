from __future__ import annotations

from base64 import b64encode
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase
from django_tenants.test.cases import TenantTestCase


class NomusHttpClientTests(SimpleTestCase):
    def test_http_client_uses_basic_auth_and_rest_paths(self):
        from apps.integrations.nomus.client import HttpNomusClient

        session = mock.Mock()
        response = mock.Mock()
        response.content = b'{"remote_id":"OP-001"}'
        response.json.return_value = {"remote_id": "OP-001"}
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = HttpNomusClient(
            base_url="https://nomus.example/erp",
            access_key="abc123",
            session=session,
        )

        result = client.upsert_production_order(
            {
                "order_number": "OF-001",
                "bom": [{"code": "MAT-1", "quantity": 2}],
                "routing": [{"operation": "CUT", "hours": "1.5"}],
            }
        )

        self.assertEqual(result["remote_id"], "OP-001")
        session.request.assert_called_once()
        call = session.request.call_args.kwargs
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://nomus.example/erp/rest/ordens-producao")
        self.assertEqual(call["json"]["order_number"], "OF-001")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(call["headers"]["Authorization"], f"Basic {b64encode(b'abc123').decode()}")

    def test_http_client_reads_order_status_from_order_resource(self):
        from apps.integrations.nomus.client import HttpNomusClient

        session = mock.Mock()
        response = mock.Mock()
        response.content = b'{"id":"OP-001","status":"liberada"}'
        response.json.return_value = {"id": "OP-001", "status": "liberada"}
        response.raise_for_status.return_value = None
        session.request.return_value = response

        client = HttpNomusClient(base_url="https://nomus.example", access_key="abc123", session=session)

        result = client.get_order_status("OP-001")

        self.assertEqual(result["status"], "liberada")
        session.request.assert_called_once()
        self.assertEqual(session.request.call_args.kwargs["url"], "https://nomus.example/rest/ordens-producao/OP-001")


class NomusMemoryClientTests(SimpleTestCase):
    def test_memory_client_persists_order_bom_and_routing(self):
        from apps.integrations.nomus.fake import MemoryNomusClient

        client = MemoryNomusClient()

        order = client.upsert_production_order({"order_number": "OF-001", "status": "planejada"})
        bom = client.upsert_bom({"bom_code": "BOM-001", "items": [{"code": "MAT-1"}]})
        routing = client.upsert_routing({"routing_code": "RTE-001", "operations": [{"code": "OP-10", "hours": 1.25}]})

        self.assertEqual(order["remote_id"], "OF-001")
        self.assertEqual(bom["remote_id"], "BOM-001")
        self.assertEqual(routing["remote_id"], "RTE-001")
        self.assertEqual(client.production_orders["OF-001"]["status"], "planejada")
        self.assertEqual(client.boms["BOM-001"]["items"][0]["code"], "MAT-1")
        self.assertEqual(client.routings["RTE-001"]["operations"][0]["code"], "OP-10")

    def test_memory_client_healthcheck_reports_counts(self):
        from apps.integrations.nomus.fake import MemoryNomusClient

        client = MemoryNomusClient()
        client.upsert_production_order({"order_number": "OF-001"})
        client.upsert_bom({"bom_code": "BOM-001"})
        client.upsert_routing({"routing_code": "RTE-001"})

        summary = client.healthcheck()

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["production_orders"], 1)
        self.assertEqual(summary["boms"], 1)
        self.assertEqual(summary["routings"], 1)
        self.assertEqual(summary["healthchecks"], 1)


class NomusIntegrationModelsTests(TenantTestCase):
    def test_integration_config_encrypts_access_key_at_rest(self):
        from apps.integrations.nomus.models import NomusIntegrationConfig

        config = NomusIntegrationConfig.objects.create(
            base_url="https://nomus.example",
            access_key="super-secret-key",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT access_key FROM {config._meta.db_table} WHERE id = %s",
                [config.pk],
            )
            stored_value = cursor.fetchone()[0]

        self.assertNotEqual(stored_value, "super-secret-key")
        self.assertEqual(
            NomusIntegrationConfig.objects.get(pk=config.pk).access_key,
            "super-secret-key",
        )

    def test_export_log_accepts_conflict_reason(self):
        from apps.integrations.nomus.models import NomusExportLog

        log = NomusExportLog.objects.create(
            remote_id="OP-001",
            conflict=True,
            conflict_reason="Remote order already exists",
        )

        self.assertTrue(log.conflict)
        self.assertEqual(log.conflict_reason, "Remote order already exists")

    def test_get_active_erp_returns_nomus_when_only_nomus_enabled(self):
        from apps.integrations.nomus.models import NomusIntegrationConfig
        from apps.integrations.routing import get_active_erp

        NomusIntegrationConfig.objects.create(
            base_url="https://nomus.example",
            access_key="token",
            enabled=True,
        )

        self.assertEqual(get_active_erp(), "nomus")

    def test_get_active_erp_returns_sap_b1_when_only_sap_b1_enabled(self):
        from apps.integrations.routing import get_active_erp
        from apps.integrations.sap_b1.models import SapB1IntegrationConfig

        SapB1IntegrationConfig.objects.create(
            enabled=True,
            base_url="https://sap.example",
            company_db="SBODEMO",
            username="manager",
            password="secret",
        )

        self.assertEqual(get_active_erp(), "sap_b1")

    def test_get_active_erp_returns_none_when_no_erp_enabled(self):
        from apps.integrations.routing import get_active_erp

        self.assertEqual(get_active_erp(), "none")
