from dataclasses import dataclass, replace

from qx.brokers.schwab.auth import SchwabAuthStatus, SchwabTokenManager
from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.models.market import BarDataRequest


@dataclass(frozen=True)
class SchwabHealthCheck:
    auth_status: SchwabAuthStatus
    market_data_ok: bool
    message: str


@dataclass(frozen=True)
class SchwabReadiness:
    label: str
    severity: str
    action: str


def schwab_readiness(status: SchwabAuthStatus) -> SchwabReadiness:
    if not status.configured:
        return SchwabReadiness(
            label="Not Configured",
            severity="error",
            action="Save Schwab client ID and secret in local settings.",
        )
    if status.restart_required:
        return SchwabReadiness(
            label="OAuth Restart Required",
            severity="error",
            action="Open Schwab authorization and save a fresh callback code.",
        )
    if not status.access_token_valid and status.refresh_token_valid:
        return SchwabReadiness(
            label="Auto Refresh Ready",
            severity="warning",
            action="Run a health check or any Schwab-backed data request to refresh the access token.",
        )
    if status.access_token_valid and status.refresh_token_valid:
        return SchwabReadiness(
            label="Ready",
            severity="success",
            action="Schwab-backed market data, options, and timing requests can run.",
        )
    return SchwabReadiness(
        label="Review Required",
        severity="warning",
        action="Review token status before relying on Schwab-backed pages.",
    )


def check_schwab_health(
    token_manager: SchwabTokenManager,
    *,
    client: SchwabApiClient | None = None,
) -> SchwabHealthCheck:
    status = token_manager.status()
    if not status.configured or status.restart_required:
        return SchwabHealthCheck(status, False, status.message)
    try:
        resolved_client = client or SchwabApiClient(
            token_manager,
            base_url=token_manager.settings.schwab_api_base_url,
        )
        bars = SchwabMarketDataProvider(resolved_client).get_daily_bars(
            BarDataRequest(symbol="SPY", period="1y")
        )
    except Exception as exc:
        if _is_refresh_token_rejection(exc):
            restart_status = replace(
                status,
                access_token_valid=False,
                refresh_token_valid=False,
                restart_required=True,
                message="Schwab refresh token was rejected. Restart OAuth authorization.",
            )
            return SchwabHealthCheck(restart_status, False, restart_status.message)
        return SchwabHealthCheck(status, False, f"Schwab market data check failed: {exc}")
    return SchwabHealthCheck(status, not bars.empty, "Schwab auth and market data are ready.")


def _is_refresh_token_rejection(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "invalid_grant",
            "refresh token is invalid",
            "expired or revoked",
            "unsupported_token_type",
        )
    )
