from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.interfaces.qx_v2 import create_qx_v2_router
from qx.pipeline.snapshot_store import CanonicalSnapshotRepository
from qx.portfolio.models import (
    AccountRiskContext,
    FreshnessState,
    PortfolioGreeks,
    PortfolioPosition,
)


NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)


class AccountProvider:
    provider_name = "test_read_only"

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    def get_account_risk_snapshot(self):
        self.calls += 1
        return self.snapshot


def account_snapshot(
    timestamp: datetime | None = None,
    *,
    account_id: str = "raw-account-123456789",
    sector_status: str = "KNOWN",
    pnl_available: bool = True,
) -> AccountRiskContext:
    timestamp = timestamp or datetime.now(timezone.utc)
    position = PortfolioPosition(
        symbol="AAPL",
        asset_class="STOCK",
        provider_sector_raw="Information Technology" if sector_status == "KNOWN" else None,
        canonical_sector_id="XLK" if sector_status == "KNOWN" else None,
        sector_status=sector_status,
        quantity=10,
        entry_price=100,
        current_price=110,
        market_value=1100,
        unrealized_pnl=100 if pnl_available else None,
        unrealized_pnl_pct=10 if pnl_available else None,
        greeks_status="AVAILABLE",
    )
    return AccountRiskContext(
        account_id=account_id,
        equity=100000,
        cash=25000,
        buying_power=50000,
        daily_realized_pnl=100 if pnl_available else 0,
        daily_unrealized_pnl=-50 if pnl_available else 0,
        daily_realized_pnl_source=100 if pnl_available else None,
        daily_unrealized_pnl_source=-50 if pnl_available else None,
        positions=[position],
        greeks=PortfolioGreeks(net_delta=10),
        sector_status=sector_status,
        pnl_status="AVAILABLE" if pnl_available else "UNAVAILABLE",
        greeks_status="AVAILABLE",
        data_as_of=timestamp,
        retrieved_at=timestamp,
        freshness=FreshnessState.FRESH,
        broker_provenance="test_read_only",
        publication_state="RESEARCH_ONLY",
        read_only=True,
        sync_status="SYNCED" if sector_status == "KNOWN" and pnl_available else "PARTIAL",
    )


def client_for(tmp_path: Path, provider: AccountProvider, repository=None) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_qx_v2_router(
            tmp_path,
            None,
            None,
            provider,
            repository or CanonicalSnapshotRepository(tmp_path / "snapshots.db"),
        )
    )
    return TestClient(app)


def test_portfolio_endpoint_uses_canonical_provider_once_and_masks_account(tmp_path):
    provider = AccountProvider(account_snapshot())

    response = client_for(tmp_path, provider).get("/api/v2/qx/portfolio")

    assert response.status_code == 200
    payload = response.json()
    assert provider.calls == 1
    assert payload["pipeline_version"] == "core_v1"
    assert payload["read_only"] is True
    assert payload["account_id"].startswith("qxacct_")
    assert "raw-account-123456789" not in response.text
    assert "client_secret" not in response.text
    assert "access_token" not in response.text
    assert payload["positions"][0]["market_value"] == 1100
    assert payload["positions"][0]["concentration_pct"] == 1.1


def test_portfolio_endpoint_historical_request_never_calls_live_provider(tmp_path):
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    past = account_snapshot(NOW - timedelta(minutes=1), account_id="past")
    future = account_snapshot(NOW + timedelta(minutes=1), account_id="future")
    repository.save_account(past, past.retrieved_at)
    repository.save_account(future, future.retrieved_at)
    provider = AccountProvider(account_snapshot(account_id="forbidden-live"))

    response = client_for(tmp_path, provider, repository).get(
        "/api/v2/qx/portfolio",
        params={"evaluation_timestamp": NOW.isoformat()},
    )

    assert response.status_code == 200
    assert provider.calls == 0
    assert response.json()["data_as_of"] == past.data_as_of.isoformat().replace("+00:00", "Z")


def test_portfolio_partial_sector_provenance_remains_explicit(tmp_path):
    provider = AccountProvider(account_snapshot(sector_status="UNKNOWN"))

    payload = client_for(tmp_path, provider).get("/api/v2/qx/portfolio").json()

    assert payload["status"] == "PARTIAL"
    assert payload["sector_status"] == "UNKNOWN"
    assert "SECTOR_PROVENANCE_INCOMPLETE" in payload["reason_codes"]
    assert payload["positions"][0]["canonical_sector_id"] is None
    assert "Unassigned" not in str(payload)


def test_portfolio_missing_pnl_stays_null_instead_of_zero(tmp_path):
    provider = AccountProvider(account_snapshot(pnl_available=False))

    payload = client_for(tmp_path, provider).get("/api/v2/qx/portfolio").json()

    assert payload["status"] == "PARTIAL"
    assert payload["daily_realized_pnl"] is None
    assert payload["daily_unrealized_pnl"] is None
    assert payload["total_unrealized_pnl"] is None
    assert "PNL_EVIDENCE_INCOMPLETE" in payload["reason_codes"]


def test_portfolio_without_account_is_truthfully_unavailable(tmp_path):
    provider = AccountProvider(None)

    payload = client_for(tmp_path, provider).get("/api/v2/qx/portfolio").json()

    assert payload["status"] == "UNAVAILABLE"
    assert payload["publication_state"] == "BLOCKED"
    assert payload["account_id"] is None
    assert payload["positions"] == []
    assert payload["reason_codes"] == ["ACCOUNT_SNAPSHOT_UNAVAILABLE"]
