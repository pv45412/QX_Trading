from datetime import UTC, datetime, timedelta
from pathlib import Path

from qx.brokers.schwab.auth import SchwabAuthStatus, SchwabToken, SchwabTokenManager, SchwabTokenStore
from qx.brokers.schwab.health import check_schwab_health, schwab_readiness
from qx.config.settings import Settings


def test_schwab_health_reports_restart_required(tmp_path: Path) -> None:
    store = SchwabTokenStore(tmp_path / "token.json")
    store.save(
        SchwabToken(
            access_token="access",
            refresh_token="refresh",
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

    health = check_schwab_health(manager)

    assert not health.market_data_ok
    assert health.auth_status.restart_required


def test_schwab_health_marks_rejected_refresh_token_as_restart_required(tmp_path: Path) -> None:
    store = SchwabTokenStore(tmp_path / "token.json")
    store.save(
        SchwabToken(
            access_token="access",
            refresh_token="refresh",
            access_token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            refresh_token_expires_at=datetime.now(UTC) + timedelta(days=1),
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

    class RejectedRefreshClient:
        def get(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError(
                'Schwab token request failed: {"error":"unsupported_token_type",'
                '"error_description":"Refresh token is invalid, expired or revoked"}'
            )

    health = check_schwab_health(manager, client=RejectedRefreshClient())  # type: ignore[arg-type]

    assert not health.market_data_ok
    assert health.auth_status.restart_required
    assert not health.auth_status.refresh_token_valid
    assert health.message == "Schwab refresh token was rejected. Restart OAuth authorization."


def test_schwab_readiness_explains_operational_state() -> None:
    not_configured = SchwabAuthStatus(
        configured=False,
        has_token=False,
        access_token_valid=False,
        refresh_token_valid=False,
        restart_required=False,
        message="Schwab client id/secret are not configured.",
        authorization_url="",
    )
    restart = SchwabAuthStatus(
        configured=True,
        has_token=True,
        access_token_valid=False,
        refresh_token_valid=False,
        restart_required=True,
        message="Schwab refresh token is expired. Restart OAuth authorization.",
        authorization_url="https://api.schwabapi.com/v1/oauth/authorize",
    )
    refresh_ready = SchwabAuthStatus(
        configured=True,
        has_token=True,
        access_token_valid=False,
        refresh_token_valid=True,
        restart_required=False,
        message="Schwab access token needs refresh.",
        authorization_url="https://api.schwabapi.com/v1/oauth/authorize",
    )
    ready = SchwabAuthStatus(
        configured=True,
        has_token=True,
        access_token_valid=True,
        refresh_token_valid=True,
        restart_required=False,
        message="Schwab token is ready.",
        authorization_url="https://api.schwabapi.com/v1/oauth/authorize",
    )

    assert schwab_readiness(not_configured).label == "Not Configured"
    assert schwab_readiness(restart).label == "OAuth Restart Required"
    assert schwab_readiness(refresh_ready).label == "Auto Refresh Ready"
    assert schwab_readiness(ready).label == "Ready"
