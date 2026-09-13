from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from qx.brokers.schwab.auth import (
    SchwabAuthError,
    SchwabToken,
    SchwabTokenManager,
    SchwabTokenStore,
    extract_authorization_code,
)
from qx.config.settings import Settings


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls = 0

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        self.calls += 1
        assert data["grant_type"] == "refresh_token"
        assert "Authorization" in headers
        return FakeResponse(
            {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 1800,
                "refresh_token_expires_in": 604800,
                "token_type": "Bearer",
            }
        )


class FakeErrorResponse:
    status_code = 400
    text = '{"error":"invalid_grant","error_description":"Authorization code is invalid, expired or revoked"}'

    def json(self) -> dict[str, Any]:
        return {}


class FakeRejectedAuthorizationHttpClient:
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        timeout: int,
    ) -> FakeErrorResponse:
        assert data["grant_type"] == "authorization_code"
        return FakeErrorResponse()


def test_token_store_round_trips(tmp_path: Path) -> None:
    store = SchwabTokenStore(tmp_path / "token.json")
    token = SchwabToken(
        access_token="access",
        refresh_token="refresh",
        access_token_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )

    store.save(token)
    loaded = store.load()

    assert loaded is not None
    assert loaded.access_token == "access"
    assert loaded.refresh_token == "refresh"


def test_token_manager_refreshes_expiring_access_token(tmp_path: Path) -> None:
    store = SchwabTokenStore(tmp_path / "token.json")
    store.save(
        SchwabToken(
            access_token="old_access",
            refresh_token="old_refresh",
            access_token_expires_at=datetime.now(UTC) + timedelta(minutes=1),
            refresh_token_expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    http = FakeHttpClient()
    manager = SchwabTokenManager(
        Settings(
            schwab_client_id="client",
            schwab_client_secret="secret",
            schwab_token_path=tmp_path / "token.json",
        ),
        store=store,
        http_client=http,
    )

    access_token = manager.get_access_token()

    assert access_token == "new_access"
    assert http.calls == 1
    assert store.load() is not None
    assert store.load().refresh_token == "new_refresh"  # type: ignore[union-attr]


def test_status_returns_authorization_url_when_token_missing(tmp_path: Path) -> None:
    manager = SchwabTokenManager(
        Settings(
            schwab_client_id="client",
            schwab_client_secret="secret",
            schwab_token_path=tmp_path / "missing.json",
        )
    )

    status = manager.status()

    assert status.configured
    assert not status.has_token
    assert status.restart_required
    assert "authorize" in status.authorization_url


def test_status_marks_expired_refresh_token_as_restart_required(tmp_path: Path) -> None:
    store = SchwabTokenStore(tmp_path / "token.json")
    store.save(
        SchwabToken(
            access_token="old_access",
            refresh_token="old_refresh",
            access_token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            refresh_token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    manager = SchwabTokenManager(
        Settings(
            schwab_client_id="client",
            schwab_client_secret="secret",
            schwab_token_path=tmp_path / "token.json",
        ),
        store=store,
    )

    status = manager.status()

    assert status.restart_required
    assert not status.refresh_token_valid


def test_extract_authorization_code_accepts_callback_url() -> None:
    value = extract_authorization_code("https://127.0.0.1/?code=abc%40&session=123")

    assert value == "abc@"


def test_extract_authorization_code_accepts_pasted_code_with_session() -> None:
    value = extract_authorization_code("abc%40&session=123")

    assert value == "abc@"


def test_exchange_authorization_code_explains_rejected_code(tmp_path: Path) -> None:
    manager = SchwabTokenManager(
        Settings(
            schwab_client_id="client",
            schwab_client_secret="secret",
            schwab_token_path=tmp_path / "token.json",
        ),
        http_client=FakeRejectedAuthorizationHttpClient(),
    )

    with pytest.raises(SchwabAuthError, match="one-time use"):
        manager.exchange_authorization_code("https://127.0.0.1/?code=abc%40&session=123")
