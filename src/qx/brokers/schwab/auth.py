from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests

from qx.config.settings import Settings


TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


class SchwabAuthError(RuntimeError):
    """Raised when Schwab credentials or token refresh are not usable."""


class HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        timeout: int,
    ) -> Any:
        """HTTP POST compatible with requests.Session.post."""


@dataclass(frozen=True)
class SchwabToken:
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime | None = None
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def needs_refresh(self) -> bool:
        return datetime.now(UTC) + TOKEN_REFRESH_BUFFER >= self.access_token_expires_at

    @property
    def refresh_expired(self) -> bool:
        return (
            self.refresh_token_expires_at is not None
            and datetime.now(UTC) >= self.refresh_token_expires_at
        )


class SchwabTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> SchwabToken | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return SchwabToken(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            access_token_expires_at=_parse_datetime(str(payload["access_token_expires_at"])),
            refresh_token_expires_at=(
                _parse_datetime(str(payload["refresh_token_expires_at"]))
                if payload.get("refresh_token_expires_at")
                else None
            ),
            token_type=str(payload.get("token_type", "Bearer")),
            scope=str(payload.get("scope", "")),
        )

    def save(self, token: SchwabToken) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "access_token_expires_at": token.access_token_expires_at.isoformat(),
            "refresh_token_expires_at": (
                token.refresh_token_expires_at.isoformat()
                if token.refresh_token_expires_at is not None
                else None
            ),
            "token_type": token.token_type,
            "scope": token.scope,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class SchwabAuthStatus:
    configured: bool
    has_token: bool
    access_token_valid: bool
    refresh_token_valid: bool
    restart_required: bool
    message: str
    authorization_url: str


class SchwabTokenManager:
    def __init__(
        self,
        settings: Settings,
        *,
        store: SchwabTokenStore | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or SchwabTokenStore(settings.schwab_token_path)
        self.http_client = http_client or requests.Session()

    def authorization_url(self) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.schwab_client_id,
                "redirect_uri": self.settings.schwab_redirect_uri,
            }
        )
        return f"{self.settings.schwab_auth_base_url}/authorize?{query}"

    def status(self) -> SchwabAuthStatus:
        configured = self._is_configured()
        token = self.store.load()
        if not configured:
            return SchwabAuthStatus(
                configured=False,
                has_token=token is not None,
                access_token_valid=False,
                refresh_token_valid=False,
                restart_required=False,
                message="Schwab client id/secret are not configured.",
                authorization_url="",
            )
        if token is None:
            return SchwabAuthStatus(
                configured=True,
                has_token=False,
                access_token_valid=False,
                refresh_token_valid=False,
                restart_required=True,
                message="No Schwab token file found. Complete browser authorization.",
                authorization_url=self.authorization_url(),
            )
        if token.refresh_expired:
            return SchwabAuthStatus(
                configured=True,
                has_token=True,
                access_token_valid=False,
                refresh_token_valid=False,
                restart_required=True,
                message="Schwab refresh token is expired. Restart OAuth authorization.",
                authorization_url=self.authorization_url(),
            )
        return SchwabAuthStatus(
            configured=True,
            has_token=True,
            access_token_valid=not token.needs_refresh,
            refresh_token_valid=not token.refresh_expired,
            restart_required=False,
            message=(
                "Schwab token is ready."
                if not token.needs_refresh
                else "Schwab access token needs refresh."
            ),
            authorization_url=self.authorization_url(),
        )

    def get_access_token(self) -> str:
        if not self._is_configured():
            raise SchwabAuthError("Schwab client id/secret are not configured.")
        token = self.store.load()
        if token is None:
            raise SchwabAuthError("No Schwab token found. Complete browser authorization first.")
        if token.refresh_expired:
            raise SchwabAuthError("Schwab refresh token expired. Complete browser authorization again.")
        if token.needs_refresh:
            token = self.refresh_access_token(token.refresh_token)
        return token.access_token

    def exchange_authorization_code(self, authorization_code: str) -> SchwabToken:
        authorization_code = extract_authorization_code(authorization_code)
        token = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": self.settings.schwab_redirect_uri,
            }
        )
        self.store.save(token)
        return token

    def refresh_access_token(self, refresh_token: str) -> SchwabToken:
        token = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )
        self.store.save(token)
        return token

    def _token_request(self, data: dict[str, str]) -> SchwabToken:
        response = self.http_client.post(
            f"{self.settings.schwab_auth_base_url}/token",
            headers={
                "Authorization": f"Basic {self._basic_auth()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=data,
            timeout=30,
        )
        if getattr(response, "status_code", 500) >= 400:
            raise SchwabAuthError(_token_error_message(data, getattr(response, "text", "")))
        payload = dict(response.json())
        return _token_from_payload(payload, fallback_refresh_token=data.get("refresh_token"))

    def _basic_auth(self) -> str:
        raw = f"{self.settings.schwab_client_id}:{self.settings.schwab_client_secret}"
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    def _is_configured(self) -> bool:
        return bool(self.settings.schwab_client_id and self.settings.schwab_client_secret)


def _token_from_payload(
    payload: dict[str, Any],
    *,
    fallback_refresh_token: str | None = None,
) -> SchwabToken:
    now = datetime.now(UTC)
    expires_in = int(payload.get("expires_in", 1800))
    refresh_expires_in = payload.get("refresh_token_expires_in")
    refresh_token = str(payload.get("refresh_token") or fallback_refresh_token or "")
    if not refresh_token:
        raise SchwabAuthError("Schwab token response did not include a refresh token.")
    return SchwabToken(
        access_token=str(payload["access_token"]),
        refresh_token=refresh_token,
        access_token_expires_at=now + timedelta(seconds=expires_in),
        refresh_token_expires_at=(
            now + timedelta(seconds=int(refresh_expires_in)) if refresh_expires_in else None
        ),
        token_type=str(payload.get("token_type", "Bearer")),
        scope=str(payload.get("scope", "")),
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def extract_authorization_code(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise SchwabAuthError("Authorization code is required.")
    if stripped.lower().startswith("http"):
        parsed = urlparse(stripped)
        values = parse_qs(parsed.query).get("code", [])
        if not values:
            raise SchwabAuthError("Callback URL did not include a code parameter.")
        return values[0]
    if "&session=" in stripped:
        stripped = stripped.split("&session=", 1)[0]
    if stripped.startswith("code="):
        stripped = stripped.split("=", 1)[1]
    return unquote(stripped)


def _token_error_message(data: dict[str, str], response_text: str) -> str:
    lowered = response_text.lower()
    grant_type = data.get("grant_type", "")
    if "invalid_grant" in lowered and grant_type == "authorization_code":
        return (
            "Schwab authorization code was rejected. Generate a fresh authorization URL, "
            "complete login, and paste the new callback URL immediately. Schwab codes are one-time use."
        )
    if "invalid_grant" in lowered and grant_type == "refresh_token":
        return "Schwab refresh token was rejected. Restart OAuth authorization."
    return f"Schwab token request failed: {response_text}"
