class BaseProtheusClient:
    """Contrato mínimo do adapter Protheus usado pelos serviços."""

    def upsert_work_order(self, payload):
        raise NotImplementedError

    def upsert_material(self, payload):
        raise NotImplementedError

    def upsert_supplier(self, payload):
        raise NotImplementedError

    def list_work_orders(self):
        raise NotImplementedError

    def list_materials(self):
        raise NotImplementedError

    def list_suppliers(self):
        raise NotImplementedError
