from datetime import date
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.db import connection
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.services import approve_quotation
from apps.integrations.protheus.client import HttpProtheusClient, HttpProtheusClientError
from apps.integrations.protheus.fake import MemoryProtheusClient
from apps.integrations.protheus.models import (
    ProtheusBOMSnapshot,
    ProtheusCatalogStaging,
    ProtheusIntegrationConfig,
    ProtheusSupplier,
    ProtheusSyncAttempt,
    ProtheusSyncBinding,
    ProtheusSyncRun,
    ProtheusWorkOrderSnapshot,
)
from apps.integrations.protheus import services
from apps.integrations.protheus.tasks import process_protheus_sync_run, pull_protheus_catalog
from apps.materials.models import Material, MaterialPrice
from apps.production import services as production_services
from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation


class ProtheusServicesTests(TenantTestCase):
    def setUp(self):
        self.client = MemoryProtheusClient()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng PE",
            role="engenheiro",
            crea_number="CREA-123",
            crea_state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe")
        approve_quotation(self.quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(self.quotation, created_by=self.user)
        self.config = ProtheusIntegrationConfig.objects.create(
            enabled=True,
            base_url="https://protheus.example/api",
            company_code="01",
            branch_code="01",
        )

    def test_enqueue_work_order_export_is_idempotent(self):
        run1, created1 = services.enqueue_work_order_export(self.of, trigger="manual")
        run2, created2 = services.enqueue_work_order_export(self.of, trigger="manual")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(run1.pk, run2.pk)
        self.assertEqual(ProtheusSyncRun.objects.count(), 1)

    def test_process_work_order_export_creates_bindings_and_attempt(self):
        run, _ = services.enqueue_work_order_export(self.of)
        services.process_sync_run(run, self.client)
        run.refresh_from_db()
        self.assertEqual(run.status, ProtheusSyncRun.STATUS_SUCCESS)
        self.assertEqual(run.remote_code, self.of.number)
        self.assertTrue(
            ProtheusSyncBinding.objects.filter(
                entity_type=ProtheusSyncBinding.ENTITY_WORK_ORDER,
                local_model="production.OrdemFabricacao",
                local_id=str(self.of.pk),
                remote_code=self.of.number,
            ).exists()
        )
        self.assertTrue(
            ProtheusSyncBinding.objects.filter(
                entity_type=ProtheusSyncBinding.ENTITY_BOM,
                local_model="production.OrdemFabricacao",
                local_id=str(self.of.pk),
            ).exists()
        )
        self.assertEqual(ProtheusSyncAttempt.objects.filter(run=run).count(), 1)

    def test_process_material_export_falls_back_to_payload_code_when_response_is_empty(self):
        material = Material.objects.create(sigla="SA-285", tipo="Chapa", forma_padrao="chapa")
        price = MaterialPrice.objects.create(
            material=material,
            forma="chapa",
            preco_brl_kg="11.00",
            fornecedor="Aco BR",
            valid_from=date(2026, 6, 24),
        )

        class EmptyMaterialClient(MemoryProtheusClient):
            def upsert_material(self, payload):
                self.materials[payload["code"]] = payload
                return {}

        run, _ = services.enqueue_material_export(material, price)
        services.process_sync_run(run, EmptyMaterialClient())

        binding = ProtheusSyncBinding.objects.get(
            entity_type=ProtheusSyncBinding.ENTITY_MATERIAL,
            local_model="materials.Material",
            local_id=str(material.pk),
        )
        self.assertEqual(binding.remote_code, "SA-285")

    def test_import_materials_upserts_catalog_and_price(self):
        payload = [{
            "code": "SA-516-70",
            "description": "Chapa carbono",
            "norm": "ASME II",
            "shape": "chapa",
            "unit_price_kg": "12.34",
            "supplier_name": "Acos Brasil",
            "valid_from": "2026-06-24",
            "is_active": True,
        }]
        imported = services.import_materials(payload)
        self.assertEqual(len(imported), 1)
        material = Material.objects.get(sigla="SA-516-70")
        price = MaterialPrice.objects.get(material=material, forma="chapa", valid_from=date(2026, 6, 24))
        self.assertEqual(material.tipo, "Chapa carbono")
        self.assertEqual(str(price.preco_brl_kg), "12.34")
        self.assertEqual(price.fornecedor, "Acos Brasil")
        self.assertTrue(
            ProtheusSyncBinding.objects.filter(
                entity_type=ProtheusSyncBinding.ENTITY_MATERIAL,
                local_model="materials.Material",
                local_id=str(material.pk),
                remote_code="SA-516-70",
            ).exists()
        )

    def test_import_suppliers_upserts_mirror(self):
        payload = [{
            "code": "FORN-001",
            "legal_name": "Fornecedor 1",
            "cnpj": "12.345.678/0001-00",
            "email": "compras@forn1.com",
            "state": "SP",
            "is_active": True,
        }]
        imported = services.import_suppliers(payload)
        self.assertEqual(len(imported), 1)
        supplier = ProtheusSupplier.objects.get(supplier_code="FORN-001")
        self.assertEqual(supplier.legal_name, "Fornecedor 1")
        self.assertTrue(
            ProtheusSyncBinding.objects.filter(
                entity_type=ProtheusSyncBinding.ENTITY_SUPPLIER,
                local_model="protheus.ProtheusSupplier",
                local_id=str(supplier.pk),
                remote_code="FORN-001",
            ).exists()
        )

    def test_import_work_orders_stages_remote_snapshot(self):
        payload = [{
            "number": "OF-EXT-001",
            "title": "OF importada",
            "customer_name": "Cliente ERP",
            "status": "liberada",
            "items": [{"code": "01", "description": "Item 1"}],
        }]
        imported = services.import_work_orders(payload)
        self.assertEqual(len(imported), 1)
        work_order = ProtheusWorkOrderSnapshot.objects.get(remote_code="OF-EXT-001")
        bom = ProtheusBOMSnapshot.objects.get(work_order=work_order)
        self.assertEqual(work_order.title, "OF importada")
        self.assertEqual(bom.payload["items"][0]["code"], "01")

    def test_pull_from_client_imports_all_supported_entities(self):
        self.client.materials["MAT-REMOTE"] = {
            "code": "MAT-REMOTE",
            "description": "Material remoto",
            "shape": "chapa",
            "unit_price_kg": "9.99",
            "supplier_name": "Fornecedor remoto",
        }
        self.client.suppliers["FORN-REMOTE"] = {
            "code": "FORN-REMOTE",
            "legal_name": "Fornecedor remoto",
        }
        self.client.work_orders["OF-EXT-001"] = {
            "number": "OF-EXT-001",
            "title": "OF importada",
            "customer_name": "Cliente ERP",
            "status": "liberada",
            "items": [{"code": "01", "description": "Item 1"}],
        }
        imported = services.pull_from_client(self.client)

        self.assertEqual(len(imported["work_orders"]), 1)
        self.assertEqual(len(imported["materials"]), 1)
        self.assertEqual(len(imported["suppliers"]), 1)
        self.assertFalse(Material.objects.filter(sigla="MAT-REMOTE").exists())
        self.assertFalse(ProtheusSupplier.objects.filter(supplier_code="FORN-REMOTE").exists())
        self.assertEqual(ProtheusCatalogStaging.objects.filter(entity_type=ProtheusCatalogStaging.ENTITY_MATERIAL).count(), 1)
        self.assertEqual(ProtheusCatalogStaging.objects.filter(entity_type=ProtheusCatalogStaging.ENTITY_SUPPLIER).count(), 1)
        work_order = ProtheusWorkOrderSnapshot.objects.get(remote_code="OF-EXT-001")
        bom = ProtheusBOMSnapshot.objects.get(work_order=work_order)
        self.assertEqual(work_order.title, "OF importada")
        self.assertEqual(bom.payload["items"][0]["code"], "01")

    def test_pull_from_client_respects_feature_flags(self):
        self.config.pull_materials_enabled = False
        self.config.pull_suppliers_enabled = False
        self.config.save(update_fields=["pull_materials_enabled", "pull_suppliers_enabled"])
        self.client.materials["MAT-01"] = {
            "code": "MAT-01",
            "description": "Material externo",
            "shape": "chapa",
            "unit_price_kg": "9.99",
        }
        self.client.suppliers["FORN-009"] = {"code": "FORN-009", "legal_name": "Fornecedor externo"}
        self.client.work_orders["OF-EXT-009"] = {
            "number": "OF-EXT-009",
            "title": "OF remota",
            "customer_name": "ERP",
            "status": "liberada",
            "items": [],
        }

        imported = services.pull_from_client(self.client, config=self.config)

        self.assertEqual(imported["materials"], [])
        self.assertEqual(imported["suppliers"], [])
        self.assertEqual(len(imported["work_orders"]), 1)
        self.assertFalse(Material.objects.filter(sigla="MAT-01").exists())
        self.assertFalse(ProtheusSupplier.objects.filter(supplier_code="FORN-009").exists())
        self.assertEqual(ProtheusCatalogStaging.objects.count(), 0)

    def test_maybe_enqueue_work_order_export_respects_enabled_config(self):
        run = services.maybe_enqueue_work_order_export(self.of, trigger="release")
        self.assertIsNotNone(run)
        self.config.export_on_release = False
        self.config.save(update_fields=["export_on_release"])
        self.assertIsNone(services.maybe_enqueue_work_order_export(self.of, trigger="release"))

    def test_pull_from_client_without_enabled_config_returns_empty(self):
        self.config.enabled = False
        self.config.save(update_fields=["enabled"])

        imported = services.pull_from_client(self.client)

        self.assertEqual(imported, {"suppliers": [], "materials": [], "work_orders": []})

    def test_stage_materials_is_idempotent_by_payload_hash(self):
        payload = [{
            "code": "SA-240-316L",
            "description": "Chapa inox",
            "shape": "chapa",
            "unit_price_kg": "33.10",
        }]

        staged1 = services.stage_materials(payload)
        staged2 = services.stage_materials(payload)

        self.assertEqual(staged1[0].pk, staged2[0].pk)
        self.assertEqual(
            ProtheusCatalogStaging.objects.filter(
                entity_type=ProtheusCatalogStaging.ENTITY_MATERIAL,
                remote_code="SA-240-316L",
            ).count(),
            1,
        )

    def test_apply_catalog_staging_updates_catalog_and_binding(self):
        staging = services.stage_materials([{
            "code": "SA-387-11",
            "description": "Chapa liga",
            "norm": "ASME II",
            "shape": "chapa",
            "unit_price_kg": "44.90",
            "supplier_name": "Liga BR",
            "valid_from": "2026-06-24",
            "is_active": True,
        }])[0]

        services.apply_catalog_staging(staging, actor=self.user)

        staging.refresh_from_db()
        material = Material.objects.get(sigla="SA-387-11")
        price = MaterialPrice.objects.get(material=material, forma="chapa", valid_from=date(2026, 6, 24))
        self.assertEqual(staging.status, ProtheusCatalogStaging.STATUS_APPLIED)
        self.assertEqual(staging.reviewed_by, self.user)
        self.assertEqual(str(price.preco_brl_kg), "44.90")
        self.assertTrue(
            ProtheusSyncBinding.objects.filter(
                entity_type=ProtheusSyncBinding.ENTITY_MATERIAL,
                local_model="materials.Material",
                local_id=str(material.pk),
                remote_code="SA-387-11",
            ).exists()
        )

    def test_reject_catalog_staging_marks_review(self):
        staging = services.stage_suppliers([{
            "code": "FORN-888",
            "legal_name": "Fornecedor 888",
            "is_active": True,
        }])[0]

        services.reject_catalog_staging(staging, actor=self.user, reason="Duplicado")

        staging.refresh_from_db()
        self.assertEqual(staging.status, ProtheusCatalogStaging.STATUS_REJECTED)
        self.assertEqual(staging.reviewed_by, self.user)
        self.assertEqual(staging.error_message, "Duplicado")


class ProtheusTasksTests(TenantTestCase):
    def setUp(self):
        self.client = MemoryProtheusClient()
        self.customer = Customer.objects.create(company_name="ACME")
        self.user = User.objects.create_user(username="eng_task")
        self.engineer = UserProfile.objects.create(
            user=self.user,
            full_name="Eng Task",
            role="engenheiro",
            crea_number="CREA-321",
            crea_state="SP",
        )
        self.quotation = create_feixe_quotation(self.customer, "Feixe Task")
        approve_quotation(self.quotation, self.engineer)
        self.of = production_services.convert_quotation_to_of(self.quotation, created_by=self.user)
        ProtheusIntegrationConfig.objects.create(
            enabled=True,
            base_url="https://protheus.example/api",
            company_code="01",
            branch_code="01",
        )

    @mock.patch("apps.integrations.protheus.tasks.build_protheus_client")
    def test_process_sync_run_task_uses_tenant_schema(self, build_client):
        run, _ = services.enqueue_work_order_export(self.of)
        build_client.return_value = self.client

        result = process_protheus_sync_run(schema_name=connection.schema_name, run_id=run.pk)

        run.refresh_from_db()
        self.assertEqual(result["run_id"], run.pk)
        self.assertEqual(run.status, ProtheusSyncRun.STATUS_SUCCESS)
        build_client.assert_called_once()

    @mock.patch("apps.integrations.protheus.tasks.build_protheus_client")
    def test_pull_catalog_task_stages_catalog_entries(self, build_client):
        self.client.materials["MAT-900"] = {
            "code": "MAT-900",
            "description": "Material remoto",
            "shape": "chapa",
            "unit_price_kg": "19.90",
        }
        self.client.suppliers["FORN-900"] = {
            "code": "FORN-900",
            "legal_name": "Fornecedor remoto",
        }
        self.client.work_orders["OF-EXT-900"] = {
            "number": "OF-EXT-900",
            "title": "OF task",
            "customer_name": "ERP",
            "status": "liberada",
            "items": [],
        }
        build_client.return_value = self.client

        summary = pull_protheus_catalog(schema_name=connection.schema_name)

        self.assertEqual(summary["materials"], 1)
        self.assertEqual(summary["suppliers"], 1)
        self.assertEqual(summary["work_orders"], 1)
        self.assertTrue(
            ProtheusCatalogStaging.objects.filter(
                entity_type=ProtheusCatalogStaging.ENTITY_MATERIAL,
                remote_code="MAT-900",
            ).exists()
        )

    def test_process_sync_run_task_marks_run_skipped_when_config_is_disabled(self):
        run, _ = services.enqueue_work_order_export(self.of)
        config = ProtheusIntegrationConfig.objects.get()
        config.enabled = False
        config.save(update_fields=["enabled"])

        result = process_protheus_sync_run(schema_name=connection.schema_name, run_id=run.pk)

        run.refresh_from_db()
        self.assertEqual(result["status"], ProtheusSyncRun.STATUS_SKIPPED)
        self.assertEqual(run.status, ProtheusSyncRun.STATUS_SKIPPED)
        self.assertEqual(run.result_payload["status"], "skipped")


class HttpProtheusClientTests(TenantTestCase):
    def test_upsert_work_order_uses_basic_auth_and_json(self):
        response = mock.Mock()
        response.content = b'{"remote_code":"OF-1","bom_code":"BOM-OF-1"}'
        response.json.return_value = {"remote_code": "OF-1", "bom_code": "BOM-OF-1"}
        response.raise_for_status.return_value = None
        session = mock.Mock()
        session.request.return_value = response
        client = HttpProtheusClient(
            base_url="https://protheus.example/api",
            auth_type="basic",
            username="user",
            password="secret",
            timeout_seconds=15,
            session=session,
        )

        payload = {"number": "OF-1"}
        result = client.upsert_work_order(payload)

        self.assertEqual(result["remote_code"], "OF-1")
        session.request.assert_called_once_with(
            method="POST",
            url="https://protheus.example/api/work-orders",
            json=payload,
            params=None,
            headers={"Accept": "application/json"},
            auth=("user", "secret"),
            timeout=15,
        )

    def test_list_materials_accepts_wrapped_payload(self):
        response = mock.Mock()
        response.content = b'{"items":[{"code":"MAT-1"}]}'
        response.json.return_value = {"items": [{"code": "MAT-1"}]}
        response.raise_for_status.return_value = None
        session = mock.Mock()
        session.request.return_value = response
        client = HttpProtheusClient(
            base_url="https://protheus.example/api",
            auth_type="token",
            token="abc",
            session=session,
        )

        items = client.list_materials()

        self.assertEqual(items, [{"code": "MAT-1"}])
        session.request.assert_called_once()
        self.assertEqual(session.request.call_args.kwargs["headers"]["Authorization"], "Bearer abc")

    def test_http_errors_raise_domain_error(self):
        session = mock.Mock()
        session.request.side_effect = requests.RequestException("boom")
        client = HttpProtheusClient(base_url="https://protheus.example/api", session=session)

        with self.assertRaises(HttpProtheusClientError):
            client.list_suppliers()
