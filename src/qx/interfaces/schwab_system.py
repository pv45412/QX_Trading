"""Local-only Schwab credential and manual OAuth controls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from qx.brokers.schwab.auth import SchwabAuthError, SchwabAuthStatus, SchwabTokenManager
from qx.brokers.schwab.config import (
    DEFAULT_SCHWAB_TOKEN_PATH,
    clear_schwab_env,
    save_schwab_env,
)
from qx.brokers.schwab.health import SchwabHealthCheck, check_schwab_health
from qx.config.settings import Settings, get_settings


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
MAX_SENSITIVE_REQUEST_BYTES = 16_384
DEFAULT_REDIRECT_URI = "https://127.0.0.1"
SensitiveRequest = TypeVar("SensitiveRequest", bound=BaseModel)


class SchwabCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=512)
    client_secret: SecretStr
    redirect_uri: str = Field(default=DEFAULT_REDIRECT_URI, min_length=1, max_length=2048)


class SchwabCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    callback_url: SecretStr


class SchwabSystemStatus(BaseModel):
    configured: bool
    client_id_last4: str | None = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    oauth_status: str = "UNAUTHENTICATED"
    refresh_token_status: str = "UNAVAILABLE"
    provider_health: str = "UNAVAILABLE"
    last_verified_at: datetime | None = None


class SchwabOAuthUrl(BaseModel):
    authorization_url: str
    security_mode: str = "MANUAL_LOCAL_CALLBACK_NO_STATE"


class SchwabSystemService:
    def __init__(
        self,
        *,
        env_path: Path = Path(".env"),
        token_path: Path = DEFAULT_SCHWAB_TOKEN_PATH,
        settings_loader: Callable[[], Settings] | None = None,
        health_check: Callable[[SchwabTokenManager], SchwabHealthCheck] = check_schwab_health,
    ) -> None:
        self.env_path = env_path
        self.token_path = token_path
        self.settings_loader = settings_loader or get_settings
        self.health_check = health_check
        self.last_health: SchwabHealthCheck | None = None
        self.last_verified_at: datetime | None = None

    def settings(self) -> Settings:
        return self.settings_loader()

    def manager(self) -> SchwabTokenManager:
        return SchwabTokenManager(self.settings)

    def status(self) -> SchwabSystemStatus:
        settings = self.settings()
        manager = self.manager()
        try:
            auth_status = (
                self.last_health.auth_status
                if self.last_health is not None
                else manager.status()
            )
        except (OSError, ValueError, KeyError, TypeError):
            auth_status = SchwabAuthStatus(
                configured=bool(settings.schwab_client_id and settings.schwab_client_secret),
                has_token=False,
                access_token_valid=False,
                refresh_token_valid=False,
                restart_required=True,
                message="Schwab authentication state is unavailable.",
                authorization_url="",
            )
        return SchwabSystemStatus(
            configured=auth_status.configured,
            client_id_last4=(
                settings.schwab_client_id[-4:] if auth_status.configured else None
            ),
            redirect_uri=settings.schwab_redirect_uri,
            oauth_status=_oauth_status(auth_status),
            refresh_token_status=_refresh_status(auth_status),
            provider_health=_provider_health(self.last_health),
            last_verified_at=self.last_verified_at,
        )

    def save(self, request: SchwabCredentialRequest) -> SchwabSystemStatus:
        previous = self.settings()
        requested_identity = (
            request.client_id.strip(),
            request.client_secret.get_secret_value().strip(),
            request.redirect_uri.strip() or DEFAULT_REDIRECT_URI,
            self.token_path,
        )
        if _credential_identity(previous) != requested_identity:
            previous.schwab_token_path.unlink(missing_ok=True)
            if self.token_path != previous.schwab_token_path:
                self.token_path.unlink(missing_ok=True)
        save_schwab_env(
            client_id=request.client_id,
            client_secret=request.client_secret.get_secret_value(),
            redirect_uri=request.redirect_uri,
            env_path=self.env_path,
        )
        self.last_health = None
        self.last_verified_at = None
        return self.status()

    def clear(self) -> SchwabSystemStatus:
        settings = self.settings()
        clear_schwab_env(self.env_path)
        settings.schwab_token_path.unlink(missing_ok=True)
        self.last_health = None
        self.last_verified_at = None
        return self.status()

    def authorization_url(self) -> SchwabOAuthUrl:
        manager = self.manager()
        status = manager.status()
        if not status.configured:
            raise ValueError("Schwab credentials are not configured.")
        return SchwabOAuthUrl(authorization_url=manager.authorization_url())

    def exchange(self, callback: SchwabCallbackRequest) -> SchwabSystemStatus:
        self.manager().exchange_authorization_code(callback.callback_url.get_secret_value())
        return self.verify()

    def verify(self) -> SchwabSystemStatus:
        self.last_health = self.health_check(self.manager())
        self.last_verified_at = datetime.now(timezone.utc)
        return self.status()


def create_schwab_system_router(
    service: SchwabSystemService | None = None,
) -> APIRouter:
    router = APIRouter()
    resolved_service = service or SchwabSystemService()

    @router.get(
        "/api/system/schwab/credentials/status",
        response_model=SchwabSystemStatus,
    )
    def credential_status(request: Request) -> SchwabSystemStatus:
        _require_local(request)
        return resolved_service.status()

    @router.post(
        "/api/system/schwab/credentials",
        response_model=SchwabSystemStatus,
    )
    async def save_credentials(request: Request) -> SchwabSystemStatus:
        _require_local_mutation(request)
        payload = await _parse_sensitive_request(
            request,
            SchwabCredentialRequest,
            "Invalid Schwab credential request.",
        )
        try:
            return resolved_service.save(payload)
        except (OSError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None

    @router.delete(
        "/api/system/schwab/credentials",
        response_model=SchwabSystemStatus,
    )
    def clear_credentials(request: Request) -> SchwabSystemStatus:
        _require_local_mutation(request)
        try:
            return resolved_service.clear()
        except OSError:
            raise HTTPException(500, "Local Schwab credentials could not be cleared.") from None

    @router.post("/api/system/schwab/test", response_model=SchwabSystemStatus)
    def test_connection(request: Request) -> SchwabSystemStatus:
        _require_local_mutation(request)
        return resolved_service.verify()

    @router.get("/api/system/schwab/oauth-url", response_model=SchwabOAuthUrl)
    def oauth_url(request: Request) -> SchwabOAuthUrl:
        _require_local(request)
        try:
            return resolved_service.authorization_url()
        except (OSError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None

    @router.post(
        "/api/system/schwab/oauth-exchange",
        response_model=SchwabSystemStatus,
    )
    async def oauth_exchange(request: Request) -> SchwabSystemStatus:
        _require_local_mutation(request)
        payload = await _parse_sensitive_request(
            request,
            SchwabCallbackRequest,
            "Invalid Schwab callback request.",
        )
        try:
            return resolved_service.exchange(payload)
        except SchwabAuthError:
            raise HTTPException(
                400,
                "Schwab authentication could not be completed. Generate a fresh callback and retry.",
            ) from None
        except (OSError, ValueError):
            raise HTTPException(400, "The Schwab callback URL is invalid.") from None

    return router


def _require_local(request: Request) -> None:
    host = request.client.host if request.client is not None else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(403, "Schwab credential controls are local-only.")


def _require_local_mutation(request: Request) -> None:
    _require_local(request)
    if request.headers.get("x-qx-local") != "1":
        raise HTTPException(403, "Local confirmation header is required.")


async def _parse_sensitive_request(
    request: Request,
    model: type[SensitiveRequest],
    error_message: str,
) -> SensitiveRequest:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > MAX_SENSITIVE_REQUEST_BYTES:
            raise HTTPException(413, "Sensitive request is too large.")
    body = await request.body()
    if len(body) > MAX_SENSITIVE_REQUEST_BYTES:
        raise HTTPException(413, "Sensitive request is too large.")
    try:
        payload = json.loads(body)
        return model.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError):
        raise HTTPException(422, error_message) from None


def _oauth_status(status: SchwabAuthStatus) -> str:
    if status.configured and status.has_token and status.refresh_token_valid:
        return "AUTHENTICATED"
    return "UNAUTHENTICATED"


def _refresh_status(status: SchwabAuthStatus) -> str:
    if not status.has_token:
        return "UNAVAILABLE"
    return "VALID" if status.refresh_token_valid else "EXPIRED"


def _provider_health(health: SchwabHealthCheck | None) -> str:
    if health is None:
        return "UNAVAILABLE"
    if health.market_data_ok:
        return "HEALTHY"
    return "DEGRADED" if health.auth_status.configured else "UNAVAILABLE"


def _credential_identity(settings: Settings) -> tuple[str, str, str, Path]:
    return (
        settings.schwab_client_id,
        settings.schwab_client_secret,
        settings.schwab_redirect_uri,
        settings.schwab_token_path,
    )
