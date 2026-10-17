import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.brokers.schwab.accounts import SchwabReadOnlyAccountSnapshotProvider
from qx.interfaces import qx_v2
from qx.options_expression.models import OptionsContext
from qx.pipeline.models import LifecycleState, QXEvaluationResult
from qx.pipeline.point_in_time import latest_visible_snapshot
from qx.pipeline.providers import SchwabCanonicalOptionChainSnapshotProvider
from qx.pipeline.snapshot_store import CanonicalSnapshotRepository
from qx.portfolio.models import AccountRiskContext, FreshnessState


NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, path, *, params=None):
        self.calls.append((path, params))
        return self.payload


class RoutingClient:
    def __init__(self, account, orders):
        self.account = account
        self.orders = orders
        self.calls = []

    def get(self, path, *, params=None):
        self.calls.append((path, params))
        return self.orders if path.endswith("/orders") else self.account


def option_payload(timestamp: datetime = NOW) -> dict:
    quote_ms = int(timestamp.timestamp() * 1000)
    return {
        "underlyingPrice": 450.0,
        "volatility": 24.0,
        "callExpDateMap": {
            "2026-09-18:2": {
                "450.0": [
                    {
                        "symbol": "SPY  260918C00450000",
                        "bid": 2.0,
                        "ask": 2.2,
                        "mark": 2.1,
                        "totalVolume": 100,
                        "openInterest": 500,
                        "volatility": 24.0,
                        "delta": 0.52,
                        "gamma": 0.03,
                        "theta": -0.11,
                        "vega": 0.18,
                        "multiplier": 100,
                        "quoteTimeInLong": quote_ms,
                    }
                ]
            }
        },
        "putExpDateMap": {},
    }


def account_payload(raw_account: str = "123456789") -> dict:
    return {
        "data": [
            {
                "securitiesAccount": {
                    "accountNumber": raw_account,
                    "currentBalances": {
                        "liquidationValue": 100000.0,
                        "cashBalance": 25000.0,
                        "buyingPower": 50000.0,
                        "dailyRealizedProfitLoss": 100.0,
                        "dailyUnrealizedProfitLoss": -50.0,
                    },
                    "openOrders": [],
                    "positions": [
                        {
                            "longQuantity": 10,
                            "shortQuantity": 0,
                            "averagePrice": 100.0,
                            "marketValue": 1100.0,
                            "longOpenProfitLoss": 100.0,
                            "instrument": {
                                "symbol": "AAPL",
                                "assetType": "EQUITY",
                                "sector": "XLK",
                            },
                        }
                    ],
                }
            }
        ]
    }


def account_snapshot(timestamp: datetime, account_id: str = "raw-account-number"):
    return AccountRiskContext(
        account_id=account_id,
        equity=100000.0,
        cash=25000.0,
        buying_power=50000.0,
        data_as_of=timestamp,
        retrieved_at=timestamp,
        freshness=FreshnessState.FRESH,
        broker_provenance="schwab_read_only",
        publication_state="RESEARCH_ONLY",
        read_only=True,
        sync_status="SYNCED",
    )


def option_snapshot(timestamp: datetime) -> OptionsContext:
    return OptionsContext(
        underlying_symbol="SPY",
        underlying_price=450.0,
        data_as_of=timestamp.isoformat(),
        source="schwab",
        freshness="FRESH",
        publication_state="RESEARCH_ONLY",
        sync_status="SYNCED",
    )


def test_canonical_option_provider_uses_one_real_chain_request_and_maps_provenance():
    client = FakeClient(option_payload())
    provider = SchwabCanonicalOptionChainSnapshotProvider(client)  # type: ignore[arg-type]

    snapshot = provider.get_option_chain_snapshot("spy")

    assert snapshot is not None
    assert len(client.calls) == 1
    assert client.calls[0][1]["contractType"] == "ALL"
    contract = snapshot.chain["2026-09-18"][450.0]["CALL"]
    assert contract.symbol == "SPY  260918C00450000"
    assert contract.contract_multiplier == 100.0
    assert contract.multiplier_provenance == "BROKER_PROVIDED"
    assert contract.greeks.provenance.value == "BROKER_PROVIDED"
    assert snapshot.source == "schwab"
    assert snapshot.sync_status == "SYNCED"


def test_canonical_spx_option_provider_uses_broker_symbol_and_preserves_identity():
    client = FakeClient(option_payload())
    provider = SchwabCanonicalOptionChainSnapshotProvider(client)  # type: ignore[arg-type]

    snapshot = provider.get_option_chain_snapshot("SPX")

    assert snapshot is not None
    assert client.calls[0][1]["symbol"] == "$SPX"
    assert snapshot.underlying_symbol == "SPX"


def test_provider_retrieved_at_occurs_after_io_completion():
    class CompletionTimedClient(FakeClient):
        def get(self, path, *, params=None):
            value = super().get(path, params=params)
            self.completed_at = datetime.now(timezone.utc)
            return value

    option_client = CompletionTimedClient(option_payload())
    option = SchwabCanonicalOptionChainSnapshotProvider(  # type: ignore[arg-type]
        option_client
    ).get_option_chain_snapshot("SPY")
    account_client = CompletionTimedClient(account_payload())
    account = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        account_client
    ).get_account_risk_snapshot()

    assert option is not None
    assert datetime.fromisoformat(option.retrieved_at) >= option_client.completed_at
    assert account is not None
    assert account.retrieved_at >= account_client.completed_at


def test_option_provider_drops_contract_without_point_in_time_quote_timestamp():
    payload = option_payload()
    del payload["callExpDateMap"]["2026-09-18:2"]["450.0"][0]["quoteTimeInLong"]
    provider = SchwabCanonicalOptionChainSnapshotProvider(FakeClient(payload))  # type: ignore[arg-type]

    assert provider.get_option_chain_snapshot("SPY") is None


def test_partial_broker_greeks_are_unavailable_not_zero_filled():
    payload = option_payload()
    del payload["callExpDateMap"]["2026-09-18:2"]["450.0"][0]["gamma"]
    provider = SchwabCanonicalOptionChainSnapshotProvider(FakeClient(payload))  # type: ignore[arg-type]

    snapshot = provider.get_option_chain_snapshot("SPY")

    assert snapshot is not None
    greeks = snapshot.chain["2026-09-18"][450.0]["CALL"].greeks
    assert greeks.provenance.value == "UNAVAILABLE"
    assert greeks.delta is greeks.gamma is greeks.theta is greeks.vega is None


@pytest.mark.parametrize("multiplier", [0, -100, "NaN"])
def test_invalid_broker_multiplier_is_not_marked_available(multiplier):
    payload = option_payload()
    payload["callExpDateMap"]["2026-09-18:2"]["450.0"][0]["multiplier"] = multiplier
    provider = SchwabCanonicalOptionChainSnapshotProvider(FakeClient(payload))  # type: ignore[arg-type]

    snapshot = provider.get_option_chain_snapshot("SPY")

    assert snapshot is not None
    contract = snapshot.chain["2026-09-18"][450.0]["CALL"]
    assert contract.contract_multiplier is None
    assert contract.multiplier_provenance == "UNAVAILABLE"


def test_read_only_account_provider_hashes_identifier_and_exposes_no_write_methods():
    raw_account = "123456789"
    provider = SchwabReadOnlyAccountSnapshotProvider(
        FakeClient(account_payload(raw_account))  # type: ignore[arg-type]
    )

    snapshot = provider.get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.account_id.startswith("qxacct_")
    assert raw_account not in snapshot.account_id
    assert snapshot.read_only is True
    assert snapshot.sync_status == "SYNCED"
    assert not hasattr(provider, "place_order")
    assert not hasattr(provider, "cancel_order")


def test_account_provider_preserves_portfolio_display_fields_without_recalculation():
    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(account_payload())
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.pnl_status == "AVAILABLE"
    assert snapshot.greeks_status == "AVAILABLE"
    assert snapshot.daily_realized_pnl_source == 100.0
    assert snapshot.daily_unrealized_pnl_source == -50.0
    assert snapshot.positions[0].market_value == 1100.0
    assert snapshot.positions[0].unrealized_pnl == 100.0
    assert snapshot.positions[0].unrealized_pnl_pct == 10.0


def test_missing_broker_pnl_remains_unavailable_in_display_provenance():
    payload = account_payload()
    balances = payload["data"][0]["securitiesAccount"]["currentBalances"]
    del balances["dailyRealizedProfitLoss"]
    del balances["dailyUnrealizedProfitLoss"]
    del payload["data"][0]["securitiesAccount"]["positions"][0][
        "longOpenProfitLoss"
    ]

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.pnl_status == "UNAVAILABLE"
    assert snapshot.daily_realized_pnl is None
    assert snapshot.daily_unrealized_pnl is None
    assert snapshot.daily_realized_pnl_source is None
    assert snapshot.daily_unrealized_pnl_source is None
    assert snapshot.positions[0].unrealized_pnl is None
    assert snapshot.sync_status == "PARTIAL"


def test_missing_open_orders_remains_unavailable_in_canonical_context():
    payload = account_payload()
    raw = payload["data"][0]
    del raw["securitiesAccount"]["openOrders"]

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.open_orders_count is None
    assert snapshot.sync_status == "PARTIAL"


def test_option_positions_force_partial_account_sync_status():
    payload = account_payload()
    position = payload["data"][0]["securitiesAccount"]["positions"][0]
    position["instrument"]["assetType"] = "OPTION"
    provider = SchwabReadOnlyAccountSnapshotProvider(FakeClient(payload))  # type: ignore[arg-type]

    snapshot = provider.get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.sync_status == "PARTIAL"


def test_unknown_sector_not_treated_as_real_sector():
    payload = account_payload()
    del payload["data"][0]["securitiesAccount"]["positions"][0]["instrument"][
        "sector"
    ]
    provider = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    )

    snapshot = provider.get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.positions[0].sector is None
    assert snapshot.positions[0].sector_status == "UNKNOWN"
    assert all(allocation.sector != "UNASSIGNED" for allocation in snapshot.sector_allocations)


def test_missing_sector_provenance_marks_account_snapshot_partial():
    payload = account_payload()
    del payload["data"][0]["securitiesAccount"]["positions"][0]["instrument"][
        "sector"
    ]

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.sector_status == "UNKNOWN"
    assert snapshot.sync_status == "PARTIAL"


def test_provider_technology_normalizes_to_xlk():
    payload = account_payload()
    payload["data"][0]["securitiesAccount"]["positions"][0]["instrument"][
        "sector"
    ] = "Information Technology"

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.positions[0].canonical_sector_id == "XLK"
    assert snapshot.positions[0].sector_status == "KNOWN"


def test_provider_financials_normalizes_to_xlf():
    payload = account_payload()
    payload["data"][0]["securitiesAccount"]["positions"][0]["instrument"][
        "sector"
    ] = "Financial Services"

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.positions[0].canonical_sector_id == "XLF"


def test_unknown_sector_remains_unmapped():
    payload = account_payload()
    payload["data"][0]["securitiesAccount"]["positions"][0]["instrument"][
        "sector"
    ] = "Broker Custom Bucket"

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.positions[0].canonical_sector_id is None
    assert snapshot.positions[0].sector_status == "UNKNOWN"
    assert snapshot.sync_status == "PARTIAL"


def test_raw_sector_value_is_preserved_for_provenance():
    payload = account_payload()
    payload["data"][0]["securitiesAccount"]["positions"][0]["instrument"][
        "sector"
    ] = "Information Technology"

    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(payload)
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.positions[0].provider_sector_raw == "Information Technology"


def test_sector_mapping_version_is_preserved():
    snapshot = SchwabReadOnlyAccountSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(account_payload())
    ).get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.sector_mapping_source == "qx_canonical_sector_taxonomy"
    assert snapshot.sector_mapping_version == "research_v1"
    assert snapshot.positions[0].sector_mapping_version == "research_v1"


def test_multiple_accounts_fail_closed_instead_of_selecting_first():
    payload = account_payload()
    payload["data"].append(account_payload("second-account")["data"][0])
    provider = SchwabReadOnlyAccountSnapshotProvider(FakeClient(payload))  # type: ignore[arg-type]

    assert provider.get_account_risk_snapshot() is None


def test_account_provider_fetches_open_orders_through_read_only_endpoint():
    payload = account_payload()
    raw = payload["data"][0]
    raw["hashValue"] = "hashed-broker-account-id"
    del raw["securitiesAccount"]["openOrders"]
    client = RoutingClient(
        payload,
        {"data": [{"status": "WORKING"}, {"status": "FILLED"}]},
    )
    provider = SchwabReadOnlyAccountSnapshotProvider(client)  # type: ignore[arg-type]

    snapshot = provider.get_account_risk_snapshot()

    assert snapshot is not None
    assert snapshot.open_orders_count == 1
    assert snapshot.sync_status == "SYNCED"
    assert len(client.calls) == 2
    assert client.calls[1][0].endswith("/orders")


def test_snapshot_repository_enforces_point_in_time_visibility(tmp_path: Path):
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    past = NOW - timedelta(minutes=1)
    future = NOW + timedelta(minutes=1)
    repository.save_option_chain(option_snapshot(past), NOW)
    repository.save_option_chain(option_snapshot(future), NOW)
    repository.save_account(account_snapshot(past), NOW)
    repository.save_account(account_snapshot(future), NOW)

    visible_option = repository.latest_option_chain("SPY", NOW)
    visible_account = repository.latest_account(NOW)

    assert visible_option is not None
    assert visible_option.data_as_of == past.isoformat()
    assert visible_account is not None
    assert visible_account.data_as_of == past


def test_snapshot_acquired_after_evaluation_is_not_visible(tmp_path: Path):
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    source_time = NOW - timedelta(minutes=1)
    acquired_after = NOW + timedelta(seconds=1)
    option = option_snapshot(source_time).model_copy(
        update={"retrieved_at": acquired_after.isoformat()}
    )
    account = account_snapshot(source_time).model_copy(update={"retrieved_at": acquired_after})
    repository.save_option_chain(option, acquired_after)
    repository.save_account(account, acquired_after)

    assert repository.latest_option_chain("SPY", NOW) is None
    assert repository.latest_account(NOW) is None


def test_snapshot_not_visible_before_retrieval_completion(tmp_path: Path):
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    retrieved_after = NOW + timedelta(seconds=1)
    option = option_snapshot(NOW - timedelta(minutes=1)).model_copy(
        update={"retrieved_at": retrieved_after.isoformat()}
    )
    repository.save_option_chain(option, retrieved_after)

    assert repository.latest_option_chain("SPY", NOW) is None
    assert repository.latest_option_chain("SPY", retrieved_after) is not None


def test_live_snapshot_visibility_requires_data_as_of_and_retrieved_at():
    visible = option_snapshot(NOW - timedelta(seconds=2)).model_copy(
        update={"retrieved_at": (NOW - timedelta(seconds=1)).isoformat()}
    )
    future_data = option_snapshot(NOW + timedelta(seconds=1)).model_copy(
        update={"retrieved_at": (NOW - timedelta(seconds=1)).isoformat()}
    )
    future_retrieval = option_snapshot(NOW - timedelta(seconds=2)).model_copy(
        update={"retrieved_at": (NOW + timedelta(seconds=1)).isoformat()}
    )

    assert qx_v2._visible_option(visible, NOW) is visible
    assert qx_v2._visible_option(future_data, NOW) is None
    assert qx_v2._visible_option(future_retrieval, NOW) is None


def test_snapshot_without_retrieval_timestamp_is_not_point_in_time_visible():
    snapshot = option_snapshot(NOW - timedelta(minutes=1))

    assert latest_visible_snapshot([snapshot], NOW, "data_as_of") is None


def test_repository_restores_retrieval_provenance_and_snapshot_ids(tmp_path: Path):
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    option_id = repository.save_option_chain(
        option_snapshot(NOW - timedelta(minutes=1)), NOW
    )
    account_id = repository.save_account(
        account_snapshot(NOW - timedelta(minutes=1)).model_copy(
            update={"retrieved_at": None}
        ),
        NOW,
    )

    option = repository.latest_option_chain("SPY", NOW)
    account = repository.latest_account(NOW)

    assert option is not None and option.retrieved_at == NOW.isoformat()
    assert option.snapshot_id == option_id
    assert account is not None and account.retrieved_at == NOW
    assert account.snapshot_id == account_id


def test_account_snapshot_persistence_never_stores_raw_account_number(tmp_path: Path):
    raw_account = "9988776655"
    database = tmp_path / "snapshots.db"
    repository = CanonicalSnapshotRepository(database)
    repository.save_account(account_snapshot(NOW, raw_account), NOW)

    raw_bytes = database.read_bytes()
    assert raw_account.encode() not in raw_bytes
    with sqlite3.connect(database) as connection:
        account_id, payload = connection.execute(
            "SELECT account_id, payload_json FROM account_snapshots"
        ).fetchone()
    assert account_id.startswith("qxacct_")
    assert raw_account not in payload


def test_snapshot_tables_preserve_core_v1_version(tmp_path: Path):
    database = tmp_path / "snapshots.db"
    repository = CanonicalSnapshotRepository(database)
    repository.save_option_chain(option_snapshot(NOW), NOW)
    repository.save_account(account_snapshot(NOW), NOW)

    with sqlite3.connect(database) as connection:
        option_version = connection.execute(
            "SELECT pipeline_version FROM option_chain_snapshots"
        ).fetchone()[0]
        account_version = connection.execute(
            "SELECT pipeline_version FROM account_snapshots"
        ).fetchone()[0]
    assert option_version == account_version == "core_v1"


def test_historical_snapshot_freshness_is_recomputed_at_evaluation_time():
    option = SchwabCanonicalOptionChainSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(option_payload(NOW))
    ).get_option_chain_snapshot("SPY")
    account = account_snapshot(NOW)

    aged_option = qx_v2._age_option_snapshot(option, NOW + timedelta(seconds=120))
    aged_account = qx_v2._age_account_snapshot(account, NOW + timedelta(seconds=120))

    assert aged_option is not None
    assert aged_option.freshness == "STALE"
    contract = aged_option.chain["2026-09-18"][450.0]["CALL"]
    assert contract.quote_age_seconds == 120.0
    assert aged_account is not None
    assert aged_account.freshness == FreshnessState.STALE_BLOCKED


def _bars(timestamp: datetime) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": timestamp,
                "open": 449.0,
                "high": 451.0,
                "low": 448.0,
                "close": 450.0,
                "volume": 1000,
            }
        ]
    )


def _result(context, config) -> QXEvaluationResult:
    return QXEvaluationResult(
        symbol=context.symbol,
        timeframe=context.timeframe,
        evaluation_timestamp=context.evaluation_timestamp,
        request_started_at=context.request_started_at,
        current_lifecycle_state=LifecycleState.NO_SETUP,
        config_version=config.version,
        data_dependencies=context.data_dependencies,
        io_metrics=context.io_metrics,
    )


def test_live_route_establishes_evaluation_after_provider_acquisition(monkeypatch, tmp_path):
    calls = 0
    captured = []
    request_time = NOW - timedelta(seconds=3)
    provider_time = NOW - timedelta(milliseconds=500)

    class Clock:
        @classmethod
        def now(cls, _timezone):
            nonlocal calls
            value = request_time + timedelta(seconds=calls)
            calls += 1
            return value

    class OptionProvider:
        provider_name = "test_option"

        def get_option_chain_snapshot(self, _symbol):
            return option_snapshot(provider_time)

    class AccountProvider:
        provider_name = "test_account"

        def get_account_risk_snapshot(self):
            return account_snapshot(provider_time, "raw-live-account")

    monkeypatch.setattr(
        qx_v2,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(NOW), 1.0, 1, 0),
    )

    def spy(context, config):
        captured.append(context)
        return _result(context, config)

    monkeypatch.setattr(qx_v2.orchestrator, "run_pipeline", spy)
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    app = FastAPI()
    app.include_router(
        qx_v2.create_qx_v2_router(
            tmp_path,
            None,
            OptionProvider(),
            AccountProvider(),
            repository,
        )
    )
    monkeypatch.setattr(qx_v2, "datetime", Clock)

    response = TestClient(app).post("/api/v2/qx/evaluate/SPY")

    assert response.status_code == 200
    context = captured[0]
    assert context.request_started_at == request_time
    assert context.evaluation_timestamp == NOW
    assert context.request_started_at < context.evaluation_timestamp
    assert context.option_chain is not None
    assert context.account_snapshot is not None
    assert context.account_snapshot.account_id.startswith("qxacct_")
    assert context.data_dependencies["option_chain"].available is True
    assert context.data_dependencies["account_snapshot"].available is True
    assert all(
        dependency.data_as_of is None
        or dependency.data_as_of <= context.evaluation_timestamp
        for dependency in context.data_dependencies.values()
    )


def test_historical_route_uses_only_stored_snapshots_and_never_live_provider(
    monkeypatch, tmp_path
):
    past = NOW - timedelta(minutes=1)
    future = NOW + timedelta(minutes=1)
    repository = CanonicalSnapshotRepository(tmp_path / "snapshots.db")
    past_option = SchwabCanonicalOptionChainSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(option_payload(past))
    ).get_option_chain_snapshot("SPY")
    future_option = SchwabCanonicalOptionChainSnapshotProvider(  # type: ignore[arg-type]
        FakeClient(option_payload(future))
    ).get_option_chain_snapshot("SPY")
    assert past_option is not None and future_option is not None
    past_option = past_option.model_copy(update={"retrieved_at": past.isoformat()})
    future_option = future_option.model_copy(update={"retrieved_at": future.isoformat()})
    repository.save_option_chain(past_option, past)
    repository.save_option_chain(future_option, future)
    repository.save_account(account_snapshot(past), NOW)
    repository.save_account(account_snapshot(future), NOW)
    captured = []

    class ForbiddenOptionProvider:
        provider_name = "forbidden"

        def get_option_chain_snapshot(self, _symbol):
            pytest.fail("historical evaluation called live option provider")

    class ForbiddenAccountProvider:
        provider_name = "forbidden"

        def get_account_risk_snapshot(self):
            pytest.fail("historical evaluation called live account provider")

    monkeypatch.setattr(
        qx_v2,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(past), 1.0, 1, 0),
    )

    def spy(context, config):
        captured.append(context)
        return _result(context, config)

    monkeypatch.setattr(qx_v2.orchestrator, "run_pipeline", spy)
    app = FastAPI()
    app.include_router(
        qx_v2.create_qx_v2_router(
            tmp_path,
            None,
            ForbiddenOptionProvider(),
            ForbiddenAccountProvider(),
            repository,
        )
    )

    response = TestClient(app).post(
        "/api/v2/qx/evaluate/SPY",
        params={"evaluation_timestamp": NOW.isoformat()},
    )

    assert response.status_code == 200
    assert captured[0].option_chain.data_as_of == past.isoformat()
    assert captured[0].account_snapshot.data_as_of == past
