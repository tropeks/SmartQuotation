from copy import deepcopy

from apps.integrations.omie.client import BaseOmieClient, payload_digest


class MemoryOmieClient(BaseOmieClient):
    def __init__(self):
        self.documents = {}
        self.issued_nfes = {}
        self.healthchecks = 0

    def issue_nfe(self, payload, *, idempotency_key=""):
        payload = deepcopy(payload)
        digest = idempotency_key or payload_digest(payload)
        remote_id = payload.get("document_number") or payload.get("order_number") or digest[:12]
        response = self.issued_nfes.get(digest)
        if response is None:
            response = {
                "remote_document_id": remote_id,
                "remote_number": f"NFE-{remote_id}",
                "status": "issued",
                "payload_digest": digest,
            }
            self.issued_nfes[digest] = deepcopy(response)
        self.documents[remote_id] = payload
        return deepcopy(response)

    def healthcheck(self):
        self.healthchecks += 1
        return {
            "status": "ok",
            "documents": len(self.documents),
            "issued": len(self.issued_nfes),
            "healthchecks": self.healthchecks,
        }
