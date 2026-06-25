from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

import requests


class BaseOmieClient:
    def issue_nfe(self, payload, *, idempotency_key=""):
        raise NotImplementedError

    def healthcheck(self):
        raise NotImplementedError


class HttpOmieClientError(RuntimeError):
    transient = False

    def __init__(self, message, *, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class HttpOmieTransientError(HttpOmieClientError):
    transient = True


class HttpOmiePermanentError(HttpOmieClientError):
    transient = False


@dataclass
class _ClientConfig:
    base_url: str
    app_key: str = ""
    app_secret: str = ""
    timeout_seconds: int = 30


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class HttpOmieClient(BaseOmieClient):
    def __init__(self, base_url, app_key="", app_secret="", timeout_seconds=30, session=None):
        self.config = _ClientConfig(
            base_url=base_url.rstrip("/"),
            app_key=app_key,
            app_secret=app_secret,
            timeout_seconds=timeout_seconds,
        )
        self.session = session or requests.Session()

    def close(self):
        self.session.close()

    def _url(self, path):
        return f"{self.config.base_url}/{path.lstrip('/')}"

    def _headers(self, *, idempotency_key=""):
        headers = {"Accept": "application/json"}
        if self.config.app_key:
            headers["X-Omie-App-Key"] = self.config.app_key
        if self.config.app_secret:
            headers["X-Omie-App-Secret"] = self.config.app_secret
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    def _request(self, method, path, payload=None, *, idempotency_key=""):
        try:
            response = self.session.request(
                method=method,
                url=self._url(path),
                json=payload,
                headers=self._headers(idempotency_key=idempotency_key),
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise HttpOmieTransientError(str(exc)) from exc
        except requests.HTTPError as exc:
            response = exc.response
            status_code = getattr(response, "status_code", None)
            error_cls = (
                HttpOmieTransientError
                if status_code in {408, 429} or (status_code and status_code >= 500)
                else HttpOmiePermanentError
            )
            raise error_cls(str(exc), status_code=status_code) from exc
        except requests.RequestException as exc:
            raise HttpOmieTransientError(str(exc)) from exc

        if not getattr(response, "content", b""):
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise HttpOmiePermanentError("Omie response is not valid JSON") from exc

    def issue_nfe(self, payload, *, idempotency_key=""):
        return self._request("POST", "/nfe/issue", payload=payload, idempotency_key=idempotency_key)

    def healthcheck(self):
        return self._request("GET", "/health")


def build_omie_client(config=None, *, session=None):
    if config is None:
        from apps.integrations.omie.services import get_enabled_config

        config = get_enabled_config()
    if config is None:
        raise HttpOmieClientError("No enabled Omie integration config was found")

    fiscal_defaults = dict(getattr(config, "fiscal_defaults", {}) or {})
    base_url = fiscal_defaults.get("base_url") or fiscal_defaults.get("api_url") or ""
    if not base_url:
        raise HttpOmiePermanentError("Omie base_url is missing in fiscal_defaults")
    return HttpOmieClient(
        base_url=base_url,
        app_key=config.app_key,
        app_secret=config.app_secret,
        timeout_seconds=config.timeout_seconds,
        session=session,
    )


def payload_digest(payload):
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
