from __future__ import annotations

from dataclasses import dataclass

import requests


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


class HttpProtheusClientError(RuntimeError):
    pass


@dataclass
class _ClientConfig:
    base_url: str
    auth_type: str = "basic"
    username: str = ""
    password: str = ""
    token: str = ""
    timeout_seconds: int = 30


class HttpProtheusClient(BaseProtheusClient):
    """Adapter HTTP para a API do Protheus."""

    def __init__(self, base_url, auth_type="basic", username="", password="", token="", timeout_seconds=30, session=None):
        self.config = _ClientConfig(
            base_url=base_url.rstrip("/"),
            auth_type=auth_type,
            username=username,
            password=password,
            token=token,
            timeout_seconds=timeout_seconds,
        )
        self.session = session or requests.Session()

    def close(self):
        self.session.close()

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.config.auth_type == "token" and self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _auth(self):
        if self.config.auth_type == "basic" and self.config.username:
            return (self.config.username, self.config.password)
        return None

    def _url(self, path):
        return f"{self.config.base_url}/{path.lstrip('/')}"

    def _request(self, method, path, payload=None, params=None):
        try:
            response = self.session.request(
                method=method,
                url=self._url(path),
                json=payload,
                params=params,
                headers=self._headers(),
                auth=self._auth(),
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise HttpProtheusClientError(str(exc)) from exc

        if not getattr(response, "content", b""):
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise HttpProtheusClientError("Protheus response is not valid JSON") from exc
        return data

    def _request_list(self, path, params=None):
        data = self._request("GET", path, params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("results", "items", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    def upsert_work_order(self, payload):
        return self._request("POST", "/work-orders", payload=payload)

    def upsert_material(self, payload):
        return self._request("POST", "/materials", payload=payload)

    def upsert_supplier(self, payload):
        return self._request("POST", "/suppliers", payload=payload)

    def list_work_orders(self):
        return self._request_list("/work-orders")

    def list_materials(self):
        return self._request_list("/materials")

    def list_suppliers(self):
        return self._request_list("/suppliers")


def build_protheus_client(config=None, *, session=None):
    from apps.integrations.protheus.services import get_enabled_config

    config = config or get_enabled_config()
    if config is None:
        raise HttpProtheusClientError("No enabled Protheus integration config was found")
    return HttpProtheusClient(
        base_url=config.base_url,
        auth_type=config.auth_type,
        username=config.username,
        password=config.password,
        token=config.token,
        timeout_seconds=config.timeout_seconds,
        session=session,
    )
