from copy import deepcopy

from apps.integrations.sap_b1.client import BaseSapB1Client, payload_digest


class MemorySapB1Client(BaseSapB1Client):
    def __init__(self):
        self.sales_orders = {}
        self.boms = {}
        self.healthchecks = 0

    def upsert_sales_order(self, payload):
        payload = deepcopy(payload)
        digest = payload_digest(payload)
        remote_code = payload.get("order_number") or payload.get("document_number") or digest[:12]
        self.sales_orders[remote_code] = payload
        return {
            "remote_code": remote_code,
            "status": "updated",
            "payload_digest": digest,
        }

    def upsert_bom(self, payload):
        payload = deepcopy(payload)
        digest = payload_digest(payload)
        remote_code = payload.get("bom_code") or payload.get("order_number") or digest[:12]
        self.boms[remote_code] = payload
        return {
            "remote_code": remote_code,
            "status": "updated",
            "payload_digest": digest,
        }

    def healthcheck(self):
        self.healthchecks += 1
        return {
            "status": "ok",
            "sales_orders": len(self.sales_orders),
            "boms": len(self.boms),
            "healthchecks": self.healthchecks,
        }

