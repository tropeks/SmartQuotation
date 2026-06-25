from copy import deepcopy

from apps.integrations.protheus.client import BaseProtheusClient


class MemoryProtheusClient(BaseProtheusClient):
    """Client fake em memória para testes e desenvolvimento local."""

    def __init__(self):
        self.work_orders = {}
        self.materials = {}
        self.suppliers = {}

    def upsert_work_order(self, payload):
        remote_code = payload["number"]
        self.work_orders[remote_code] = deepcopy(payload)
        return {
            "remote_code": remote_code,
            "bom_code": f"BOM-{remote_code}",
            "status": "updated",
        }

    def upsert_material(self, payload):
        remote_code = payload["code"]
        self.materials[remote_code] = deepcopy(payload)
        return {"remote_code": remote_code, "status": "updated"}

    def upsert_supplier(self, payload):
        remote_code = payload["code"]
        self.suppliers[remote_code] = deepcopy(payload)
        return {"remote_code": remote_code, "status": "updated"}

    def list_work_orders(self):
        return [deepcopy(item) for item in self.work_orders.values()]

    def list_materials(self):
        return [deepcopy(item) for item in self.materials.values()]

    def list_suppliers(self):
        return [deepcopy(item) for item in self.suppliers.values()]

    def healthcheck(self):
        return {
            "status": "ok",
            "work_orders": len(self.work_orders),
            "materials": len(self.materials),
            "suppliers": len(self.suppliers),
        }
