from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
import json

import requests


class BaseNomusClient:
    def upsert_production_order(self, payload):
        raise NotImplementedError

    def upsert_bom(self, payload):
        raise NotImplementedError

    def upsert_routing(self, payload):
        raise NotImplementedError

    def get_order_status(self, remote_id):
        raise NotImplementedError

    def healthcheck(self):
        raise NotImplementedError


class HttpNomusClientError(RuntimeError):
    transient = False

    def __init__(self, message, *, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class HttpNomusTransientError(HttpNomusClientError):
    transient = True


class HttpNomusPermanentError(HttpNomusClientError):
    transient = False


@dataclass
class _ClientConfig:
    base_url: str
    access_key: str = ""
    timeout_seconds: int = 30


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_digest(payload):
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class HttpNomusClient(BaseNomusClient):
    def __init__(self, base_url, access_key="", timeout_seconds=30, session=None):
        self.config = _ClientConfig(
            base_url=base_url.rstrip("/"),
            access_key=access_key,
            timeout_seconds=timeout_seconds,
        )
        self.session = session or requests.Session()

    def close(self):
        self.session.close()

    def _url(self, path):
        return f"{self.config.base_url}/{path.lstrip('/')}"

    def _headers(self):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.config.access_key:
            encoded_key = b64encode(self.config.access_key.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded_key}"
        return headers

    def _request(self, method, path, payload=None):
        try:
            response = self.session.request(
                method=method,
                url=self._url(path),
                json=payload,
                headers=self._headers(),
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise HttpNomusTransientError(str(exc)) from exc
        except requests.HTTPError as exc:
            response = exc.response
            status_code = getattr(response, "status_code", None)
            error_cls = (
                HttpNomusTransientError
                if status_code in {408, 429} or (status_code and status_code >= 500)
                else HttpNomusPermanentError
            )
            raise error_cls(str(exc), status_code=status_code) from exc
        except requests.RequestException as exc:
            raise HttpNomusTransientError(str(exc)) from exc

        if not getattr(response, "content", b""):
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise HttpNomusPermanentError("Nomus response is not valid JSON") from exc

    def upsert_production_order(self, payload):
        return self._request("POST", "/rest/ordens-producao", payload=payload)

    def upsert_bom(self, payload):
        return self._request("POST", "/rest/listas-materiais", payload=payload)

    def upsert_routing(self, payload):
        return self._request("POST", "/rest/roteiros", payload=payload)

    def get_order_status(self, remote_id):
        return self._request("GET", f"/rest/ordens-producao/{remote_id}")

    def healthcheck(self):
        return self._request("GET", "/health")


def build_nomus_client(*, base_url, access_key="", timeout_seconds=30, session=None):
    return HttpNomusClient(
        base_url=base_url,
        access_key=access_key,
        timeout_seconds=timeout_seconds,
        session=session,
    )

