from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.services import approve_quotation
from apps.integrations.protheus.fake import MemoryProtheusClient
from apps.integrations.protheus.models import (
    ProtheusBOMSnapshot,
    ProtheusIntegrationConfig,
    ProtheusSupplier,
    ProtheusSyncAttempt,
    ProtheusSyncBinding,
    ProtheusSyncRun,
    ProtheusWorkOrderSnapshot,
)
from apps.integrations.protheus import services
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
        local_material = Material.objects.create(sigla="SA-179", tipo="Tubo", forma_padrao="tubo")
        local_price = MaterialPrice.objects.create(
            material=local_material,
            forma="tubo",
            preco_brl_kg="10.50",
            fornecedor="Tubos BR",
            valid_from=date(2026, 6, 24),
        )
        supplier = ProtheusSupplier.objects.create(supplier_code="FORN-002", legal_name="Fornecedor 2")
        work_order_run, _ = services.enqueue_work_order_export(self.of)
        services.process_sync_run(work_order_run, self.client)
        material_run, _ = services.enqueue_material_export(local_material, local_price)
        services.process_sync_run(material_run, self.client)
        supplier_run, _ = services.enqueue_supplier_export(supplier)
        services.process_sync_run(supplier_run, self.client)

        imported = services.pull_from_client(self.client)

        self.assertEqual(len(imported["work_orders"]), 1)
        self.assertGreaterEqual(len(imported["materials"]), 1)
        self.assertGreaterEqual(len(imported["suppliers"]), 1)

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
