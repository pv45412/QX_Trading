from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests

from qx.config.settings import Settings


TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


class SchwabAuthError(RuntimeError):
    """Raised when Schwab credentials or token refresh are not usable."""


# Schwab's own rejection text from the most recent refresh-grant attempt, keyed by
# the token file path. This lives at module scope on purpose: the settings page,
# the health probes and the API client each build their own short-lived
# SchwabTokenManager, so an instance attribute would be set by one object and read
# by another and the dead grant would never surface. Entries are removed the
# instant any token request succeeds, so a fresh browser authorization clears it.
_PROVIDER_REJECTIONS: dict[str, tuple[str, float]] = {}

# Token paths that have completed a token request successfully during this process.
# This is positive evidence the grant works, as opposed to "no failure seen yet".
_PROVIDER_CONFIRMED: set[str] = set()


def _rejection_key(settings: Settings) -> str:
    return str(settings.schwab_token_path)


def _record_provider_rejection(settings: Settings, message: str) -> None:
    _PROVIDER_REJECTIONS[_rejection_key(settings)] = (message, time.time())
    _PROVIDER_CONFIRMED.discard(_rejection_key(settings))


def _clear_provider_rejection(settings: Settings) -> None:
    _PROVIDER_REJECTIONS.pop(_rejection_key(settings), None)
    _PROVIDER_CONFIRMED.add(_rejection_key(settings))


def _provider_rejection(settings: Settings) -> str | None:
    entry = _PROVIDER_REJECTIONS.get(_rejection_key(settings))
    return entry[0] if entry else None


def _provider_confirmed(settings: Settings) -> bool:
    return _rejection_key(settings) in _PROVIDER_CONFIRMED


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
    def refresh_expiry_known(self) -> bool:
        """True when Schwab told us when the refresh token dies.

        Schwab's refresh_token grant omits ``refresh_token_expires_in``, so a
        token produced by a refresh has no known refresh expiry. That is an
        UNKNOWN, not a pass — callers must not render it as "valid".
        """
        return self.refresh_token_expires_at is not None

    @property
    def refresh_expired(self) -> bool:
        """True only when we KNOW the refresh token is past its expiry."""
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
    # Tri-state honesty fields. ``refresh_token_valid`` is a bool and therefore
    # cannot express "Schwab never told us when this refresh token dies", which
    # is the normal state after a refresh grant. These carry the real answer.
    refresh_expiry_known: bool = True
    refresh_token_state: str = "unknown"  # valid | expired | unknown | absent
    provider_verified: bool = False
    provider_error: str | None = None


class SchwabTokenManager:
    def __init__(
        self,
        settings: Settings | Callable[[], Settings],
        *,
        store: SchwabTokenStore | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self.http_client = http_client or requests.Session()
        # Schwab's own rejection text from the most recent refresh attempt. Kept on
        # the module registry as well as the instance because the settings page and
        # the health probes each build their own short-lived manager; the instance
        # value only survives for objects that live long enough to be asked.
        self._last_provider_error: str | None = None

    @property
    def settings(self) -> Settings:
        return self._settings() if callable(self._settings) else self._settings

    @property
    def store(self) -> SchwabTokenStore:
        return self._store or SchwabTokenStore(self.settings.schwab_token_path)

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
                refresh_expiry_known=False,
                refresh_token_state="absent",
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
                refresh_expiry_known=False,
                refresh_token_state="absent",
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
                refresh_expiry_known=True,
                refresh_token_state="expired",
            )
        expiry_known = token.refresh_expiry_known
        state = "valid" if expiry_known else "unknown"
        rejected = _provider_rejection(self.settings)
        if rejected:
            # Schwab itself refused the refresh grant. The stored file may still
            # look healthy on paper, but the grant is dead, so report that instead
            # of "ready" and letting the next real request fail.
            return SchwabAuthStatus(
                configured=True,
                has_token=True,
                access_token_valid=not token.needs_refresh,
                refresh_token_valid=False,
                restart_required=True,
                message=(
                    "Schwab rejected the stored refresh token. The saved grant is dead; "
                    "complete browser authorization again to replace it."
                ),
                authorization_url=self.authorization_url(),
                refresh_expiry_known=expiry_known,
                refresh_token_state="rejected",
                provider_verified=False,
                provider_error=rejected,
            )
        if not token.needs_refresh:
            message = "Schwab access token is ready."
        elif expiry_known:
            message = "Schwab access token needs refresh; the refresh token is still valid."
        else:
            message = (
                "Schwab access token needs refresh. Schwab did not report a refresh "
                "token expiry, so its remaining life is unknown until a refresh is "
                "attempted."
            )
        return SchwabAuthStatus(
            configured=True,
            has_token=True,
            access_token_valid=not token.needs_refresh,
            refresh_token_valid=not token.refresh_expired,
            restart_required=False,
            message=message,
            authorization_url=self.authorization_url(),
            refresh_expiry_known=expiry_known,
            refresh_token_state=state,
            provider_verified=_provider_confirmed(self.settings),
            provider_error=self._last_provider_error,
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
            message = _token_error_message(data, getattr(response, "text", ""))
            # Remember the provider's rejection so status() can report it and the
            # settings page stops claiming a dead grant merely "needs refresh".
            self._last_provider_error = message
            _record_provider_rejection(self.settings, message)
            raise SchwabAuthError(message)
        payload = dict(response.json())
        self._last_provider_error = None
        _clear_provider_rejection(self.settings)
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
