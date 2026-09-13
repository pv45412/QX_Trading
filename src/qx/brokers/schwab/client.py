from __future__ import annotations

from typing import Any

import requests

from qx.brokers.schwab.auth import SchwabTokenManager


class SchwabApiClient:
    """Small authenticated Schwab REST client with automatic token refresh."""

    def __init__(
        self,
        token_manager: SchwabTokenManager,
        *,
        base_url: str,
        session: requests.Session | None = None,
    ) -> None:
        self.token_manager = token_manager
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {self.token_manager.get_access_token()}"},
            params=params,
            timeout=30,
        )
        if response.status_code >= 400:
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return {"data": payload}
        return dict(payload)
