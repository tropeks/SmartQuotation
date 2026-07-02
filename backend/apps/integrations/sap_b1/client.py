from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

import requests


class BaseSapB1Client:
    def upsert_sales_order(self, payload):
        raise NotImplementedError

    def upsert_bom(self, payload):
        raise NotImplementedError

    def get_sales_order_status(self, sap_doc_entry):
        raise NotImplementedError

    def healthcheck(self):
        raise NotImplementedError


class HttpSapB1ClientError(RuntimeError):
    transient = False

    def __init__(self, message, *, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class HttpSapB1TransientError(HttpSapB1ClientError):
    transient = True


class HttpSapB1PermanentError(HttpSapB1ClientError):
    transient = False


@dataclass
class _ClientConfig:
    base_url: str
    username: str = ""
    password: str = ""
    company_db: str = ""
    timeout_seconds: int = 30


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_digest(payload):
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class HttpSapB1Client(BaseSapB1Client):
    def __init__(self, base_url, username="", password="", company_db="", timeout_seconds=30, session=None):
        self.config = _ClientConfig(
            base_url=base_url.rstrip("/"),
            username=username,
            password=password,
            company_db=company_db,
            timeout_seconds=timeout_seconds,
        )
        self.session = session or requests.Session()
        self._authenticated = False

    def close(self):
        self.session.close()

    def _url(self, path):
        base_url = self.config.base_url.rstrip("/")
        if base_url.endswith("/b1s/v1") or base_url.endswith("/b1s/v2"):
            root = base_url
        else:
            root = f"{base_url}/b1s/v2"
        return f"{root}/{path.lstrip('/')}"

    def _headers(self):
        return {"Accept": "application/json"}

    def _classify_http_error(self, exc):
        response = exc.response
        status_code = getattr(response, "status_code", None)
        error_cls = (
            HttpSapB1TransientError
            if status_code in {408, 429} or (status_code and status_code >= 500)
            else HttpSapB1PermanentError
        )
        return error_cls(str(exc), status_code=status_code)

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
            raise HttpSapB1TransientError(str(exc)) from exc
        except requests.HTTPError as exc:
            raise self._classify_http_error(exc) from exc
        except requests.RequestException as exc:
            raise HttpSapB1TransientError(str(exc)) from exc

        if not getattr(response, "content", b""):
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise HttpSapB1PermanentError("SAP B1 response is not valid JSON") from exc

    def login(self):
        if self._authenticated or not (self.config.username or self.config.password):
            self._authenticated = True
            return {}
        response = self._request(
            "POST",
            "/Login",
            payload={
                "CompanyDB": self.config.company_db,
                "UserName": self.config.username,
                "Password": self.config.password,
            },
        )
        self._authenticated = True
        return response

    def _ensure_login(self):
        if not self._authenticated:
            self.login()

    def upsert_sales_order(self, payload):
        self._ensure_login()
        sap_doc_entry = payload.get("sap_doc_entry")
        if sap_doc_entry:
            return self._request("PATCH", f"/Orders({sap_doc_entry})", payload=payload)
        return self._request("POST", "/Orders", payload=payload)

    def upsert_bom(self, payload):
        self._ensure_login()
        return self._request("POST", "/ProductTrees", payload=payload)

    def get_sales_order_status(self, sap_doc_entry):
        self._ensure_login()
        return self._request("GET", f"/Orders({sap_doc_entry})")

    def healthcheck(self):
        self._ensure_login()
        return self._request("GET", "/CompanyService_GetCompanyInfo")


def build_sap_b1_client(config=None, *, session=None):
    if config is None:
        from apps.integrations.sap_b1.services import get_enabled_config

        config = get_enabled_config()
    if config is None:
        raise HttpSapB1ClientError("No enabled SAP B1 integration config was found")
    return HttpSapB1Client(
        base_url=config.base_url,
        username=config.username,
        password=config.password,
        company_db=config.company_db,
        timeout_seconds=config.timeout_seconds,
        session=session,
    )
