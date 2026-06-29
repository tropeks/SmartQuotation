from __future__ import annotations

import base64
from datetime import timedelta

import requests
from django.utils import timezone


BLING_BASE_URL = "https://api.bling.com.br/Api/v3"
_TIMEOUT = 30
_TRANSIENT_STATUSES = {408, 429}
_TOKEN_REFRESH_BUFFER = timedelta(seconds=60)


class BlingClientError(RuntimeError):
    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class BlingTransientError(BlingClientError):
    """Raised for transient network/server failures that Celery should retry."""


class BaseBlingClient:
    def oauth_refresh_token(self, client_id, client_secret, refresh_token):
        raise NotImplementedError

    def get_headers(self):
        raise NotImplementedError

    def post_nfe(self, payload):
        raise NotImplementedError

    def get_nfe_status(self, nfe_id):
        raise NotImplementedError

    def ping(self):
        raise NotImplementedError


class BlingClient(BaseBlingClient):
    def __init__(self, config, *, base_url=BLING_BASE_URL, session=None):
        self.config = config
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = _TIMEOUT

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_fresh_token(self):
        expires_at = self.config.token_expires_at
        if expires_at is None:
            return
        if timezone.now() >= expires_at - _TOKEN_REFRESH_BUFFER:
            self.oauth_refresh_token(
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                refresh_token=self.config.refresh_token,
            )

    def oauth_refresh_token(self, client_id, client_secret, refresh_token):
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        response = self._request(
            "POST",
            "/oauth/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        access_token = response["access_token"]
        expires_in = response.get("expires_in", 3600)
        expires_at = timezone.now() + timedelta(seconds=expires_in)
        self.config.access_token = access_token
        self.config.token_expires_at = expires_at
        self.config.save(update_fields=["access_token", "token_expires_at"])

    def post_nfe(self, payload):
        return self._request("POST", "/nfe", json=payload)

    def get_nfe_status(self, nfe_id):
        return self._request("GET", f"/nfe/{nfe_id}")

    def ping(self):
        return self._request("GET", "/ping")

    def _request(self, method, path, **kwargs):
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = kwargs.pop("headers", None)
        _use_auth = headers is None
        if _use_auth:
            self._ensure_fresh_token()
            headers = self.get_headers()
        try:
            resp = self._session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
            resp.raise_for_status()
            if not getattr(resp, "content", b""):
                return {}
            return resp.json()
        except requests.HTTPError as exc:
            resp = exc.response
            status = resp.status_code if resp is not None else None
            if status == 401 and _use_auth:
                self.oauth_refresh_token(
                    client_id=self.config.client_id,
                    client_secret=self.config.client_secret,
                    refresh_token=self.config.refresh_token,
                )
                try:
                    resp2 = self._session.request(
                        method=method,
                        url=url,
                        headers=self.get_headers(),
                        timeout=self._timeout,
                        **kwargs,
                    )
                    resp2.raise_for_status()
                    if not getattr(resp2, "content", b""):
                        return {}
                    return resp2.json()
                except requests.HTTPError as exc2:
                    resp2 = exc2.response
                    status2 = resp2.status_code if resp2 is not None else None
                    if status2 in _TRANSIENT_STATUSES or (status2 is not None and status2 >= 500):
                        raise BlingTransientError(str(exc2)) from exc2
                    raise BlingClientError(str(exc2), status_code=status2) from exc2
                except requests.RequestException as exc2:
                    raise BlingTransientError(str(exc2)) from exc2
            if status in _TRANSIENT_STATUSES or (status is not None and status >= 500):
                raise BlingTransientError(str(exc)) from exc
            raise BlingClientError(str(exc), status_code=status) from exc
        except requests.RequestException as exc:
            raise BlingTransientError(str(exc)) from exc

    def close(self):
        self._session.close()


class BlingFakeClient(BaseBlingClient):
    def __init__(self, config):
        self.config = config
        self._nfes = {}
        self._next_id = 1

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }

    def oauth_refresh_token(self, client_id, client_secret, refresh_token):
        fake_token = f"fake-access-{client_id}-refreshed"
        expires_at = timezone.now() + timedelta(hours=1)
        self.config.access_token = fake_token
        self.config.token_expires_at = expires_at
        self.config.save(update_fields=["access_token", "token_expires_at"])

    def post_nfe(self, payload):
        nfe_id = self._next_id
        self._next_id += 1
        self._nfes[nfe_id] = {"id": nfe_id, "situacao": {"valor": 100}, "payload": payload}
        return {"id": nfe_id, "situacao": {"valor": 100}}

    def get_nfe_status(self, nfe_id):
        nfe_id_int = int(nfe_id)
        if nfe_id_int in self._nfes:
            return self._nfes[nfe_id_int]
        return {"id": nfe_id_int, "situacao": {"valor": 100}}

    def ping(self):
        return {"status": "ok"}
