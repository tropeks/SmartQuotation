from copy import deepcopy

from apps.integrations.nomus.client import BaseNomusClient, payload_digest


class MemoryNomusClient(BaseNomusClient):
    def __init__(self):
        self.production_orders = {}
        self.boms = {}
        self.routings = {}
        self.healthchecks = 0

    def upsert_production_order(self, payload):
        payload = deepcopy(payload)
        digest = payload_digest(payload)
        remote_id = payload.get("remote_id") or payload.get("order_number") or payload.get("document_number") or digest[:12]
        self.production_orders[remote_id] = payload
        return {
            "remote_id": remote_id,
            "status": "updated",
            "payload_digest": digest,
        }

    def upsert_bom(self, payload):
        payload = deepcopy(payload)
        digest = payload_digest(payload)
        remote_id = payload.get("remote_id") or payload.get("bom_code") or payload.get("order_number") or digest[:12]
        self.boms[remote_id] = payload
        return {
            "remote_id": remote_id,
            "status": "updated",
            "payload_digest": digest,
        }

    def upsert_routing(self, payload):
        payload = deepcopy(payload)
        digest = payload_digest(payload)
        remote_id = payload.get("remote_id") or payload.get("routing_code") or payload.get("order_number") or digest[:12]
        self.routings[remote_id] = payload
        return {
            "remote_id": remote_id,
            "status": "updated",
            "payload_digest": digest,
        }

    def get_order_status(self, remote_id):
        payload = self.production_orders.get(remote_id, {})
        return {
            "id": remote_id,
            "status": payload.get("status", "planejada"),
        }

    def healthcheck(self):
        self.healthchecks += 1
        return {
            "status": "ok",
            "production_orders": len(self.production_orders),
            "boms": len(self.boms),
            "routings": len(self.routings),
            "healthchecks": self.healthchecks,
        }

