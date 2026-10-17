from datetime import datetime, timezone

import pandas as pd
import pytest

from qx.brokers.schwab.movers import normalize_screeners, fetch_top_movers
from qx.data.metadata import SymbolMetadataStore
from qx.data.quotes import QuoteSnapshot


def row(**updates):
    return {"symbol": "TEST", "lastPrice": 99., "netChange": -1., **updates}


@pytest.mark.parametrize("updates", [{"lastPrice": float("nan")}, {"netChange": True}, {"lastPrice": 0}, {"netChange": 100}, {"symbol": ""}])
def test_invalid_prices_fail_closed(updates):
    with pytest.raises(ValueError):
        normalize_screeners({"screeners": [row(**updates)]})


def test_negative_highest_mover_is_not_relabelled_as_gainer():
    class Client:
        def get(self, path, params):
            assert path == "/marketdata/v1/movers/$SPX"
            return {"screeners": [row()]}
    result = fetch_top_movers(Client())
    assert result["groups"]["highest"][0]["return"] == pytest.approx(-.01)
    assert result["market_as_of"] is None


def test_duplicates_and_missing_list_rejected():
    for payload in ({}, {"screeners": [row(), row()]}):
        with pytest.raises(ValueError):
            normalize_screeners(payload)


def test_request_guard_and_sanitized_failure(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request
    from qx.interfaces import web
    endpoint = next(r.endpoint for r in web.create_app().routes if r.path == "/api/schwab/movers")
    with pytest.raises(HTTPException) as error:
        endpoint(Request({"type": "http", "headers": []}))
    assert error.value.status_code == 403
    def fail(*args):
        raise RuntimeError("private broker error")
    monkeypatch.setattr(web, "_schwab_client", fail)
    with pytest.raises(HTTPException) as error:
        endpoint(Request({"type": "http", "headers": [(b"x-qx-refresh", b"1")]}))
    assert error.value.status_code == 503
    assert "private" not in error.value.detail


def test_movers_are_enriched_with_metadata_and_live_spy_benchmark(tmp_path):
    metadata_path = tmp_path / "symbol_metadata.csv"
    pd.DataFrame(
        [{
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Information Technology",
            "industry": "Technology Hardware",
        }]
    ).to_csv(metadata_path, index=False)

    class Client:
        def get(self, path, params):
            assert path == "/marketdata/v1/movers/$SPX"
            return {
                "screeners": [{
                    "symbol": "AAPL",
                    "description": "APPLE INC",
                    "lastPrice": 250.0,
                    "netChange": 5.0,
                    "netPercentChange": 2.04,
                    "volume": 1_000_000,
                    "totalVolume": 2_000_000,
                    "trades": 25_000,
                    "marketShare": 1.5,
                }]
            }

    class QuoteProvider:
        provider_name = "schwab"

        def get_quote(self, symbol):
            assert symbol == "SPY"
            return QuoteSnapshot(
                symbol="SPY",
                provider="schwab",
                change_pct=0.011,
                timestamp=datetime(2026, 9, 17, 19, 33, tzinfo=timezone.utc),
            )

    result = fetch_top_movers(
        Client(),
        metadata_store=SymbolMetadataStore(metadata_path),
        benchmark_quote_provider=QuoteProvider(),
    )

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["name"] == "APPLE INC"
    assert row["name_source"] == "schwab:movers.description"
    assert row["sector"] == "Information Technology"
    assert row["industry"] == "Technology Hardware"
    assert row["return_1d"] == pytest.approx(5 / 245)
    assert row["benchmark_return_1d"] == pytest.approx(0.011)
    assert row["excess_1d"] == pytest.approx((5 / 245) - 0.011)
    assert row["benchmark_source"] == "schwab:quote:SPY"
    assert row["last"] == 250.0
    assert row["volume"] == 1_000_000


def test_failed_benchmark_and_unknown_metadata_remain_unavailable(tmp_path):
    class Client:
        def get(self, path, params):
            return {"screeners": [row(symbol="ZZZZ")]}

    class QuoteProvider:
        provider_name = "schwab"

        def get_quote(self, symbol):
            raise RuntimeError("quote unavailable")

    result = fetch_top_movers(
        Client(),
        metadata_store=SymbolMetadataStore(tmp_path / "missing.csv"),
        benchmark_quote_provider=QuoteProvider(),
    )
    mover = result["rows"][0]
    assert mover["sector"] is None
    assert mover["industry"] is None
    assert mover["excess_1d"] is None
    assert mover["benchmark_source"] == "UNAVAILABLE"
