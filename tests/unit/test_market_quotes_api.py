from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.config.rules_config import RulesEngineConfig
from qx.data.quotes import QuoteSnapshot
from qx.interfaces import web
from qx.interfaces.market_quotes import create_market_quotes_router


NOW = datetime(2026, 9, 17, 14, 30, tzinfo=timezone.utc)


class StaticQuoteProvider:
    def __init__(self, quote: QuoteSnapshot) -> None:
        self.quote = quote
        self.requested_symbols: list[str] = []

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self.requested_symbols.append(symbol)
        return self.quote


class FailingQuoteProvider:
    def get_quote(self, symbol: str) -> QuoteSnapshot:
        raise RuntimeError("client_secret=do-not-leak access_token=do-not-leak")


def _client(provider: object, *, max_age_seconds: float = 60.0) -> TestClient:
    config = RulesEngineConfig()
    config.direction_engine.freshness.quote_max_age_seconds = max_age_seconds
    app = FastAPI()
    app.include_router(
        create_market_quotes_router(
            provider,  # type: ignore[arg-type]
            config=config,
            now=lambda: NOW,
        )
    )
    return TestClient(app)


def test_quote_api_returns_provider_values_without_fabrication() -> None:
    quote = QuoteSnapshot(
        symbol="SPY",
        resolved_symbol="SPY",
        asset_type="EQUITY",
        provider="schwab",
        last=662.14,
        bid=662.13,
        ask=662.15,
        change_pct=0.0042,
        volume=53_210_987.0,
        timestamp=NOW - timedelta(seconds=12),
        trade_timestamp=NOW - timedelta(seconds=13),
        realtime=True,
    )
    provider = StaticQuoteProvider(quote)

    response = _client(provider).get("/api/v2/market/quote/spy")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "SPY",
        "resolved_symbol": "SPY",
        "asset_type": "EQUITY",
        "source": "schwab",
        "status": "AVAILABLE",
        "last": 662.14,
        "bid": 662.13,
        "ask": 662.15,
        "change_pct": 0.0042,
        "volume": 53_210_987.0,
        "quote_timestamp": "2026-09-17T14:29:48Z",
        "trade_timestamp": "2026-09-17T14:29:47Z",
        "realtime": True,
        "retrieved_at": "2026-09-17T14:30:00Z",
        "age_seconds": 12.0,
        "freshness": "FRESH",
        "field_evidence": {
            "last": {"availability": "AVAILABLE", "source": "schwab", "reason_code": None},
            "bid": {"availability": "AVAILABLE", "source": "schwab", "reason_code": None},
            "ask": {"availability": "AVAILABLE", "source": "schwab", "reason_code": None},
            "change_pct": {"availability": "AVAILABLE", "source": "schwab", "reason_code": None},
            "volume": {"availability": "AVAILABLE", "source": "schwab", "reason_code": None},
        },
    }
    assert provider.requested_symbols == ["SPY"]


def test_spx_preserves_schwab_resolved_symbol() -> None:
    provider = StaticQuoteProvider(
        QuoteSnapshot(
            symbol="SPX",
            resolved_symbol="$SPX",
            asset_type="INDEX",
            provider="schwab",
            last=6888.25,
            timestamp=NOW,
        )
    )

    response = _client(provider).get("/api/v2/market/quote/SPX")

    assert response.status_code == 200
    assert response.json()["symbol"] == "SPX"
    assert response.json()["resolved_symbol"] == "$SPX"
    assert response.json()["asset_type"] == "INDEX"
    assert response.json()["bid"] is None
    assert response.json()["ask"] is None
    assert response.json()["field_evidence"]["bid"] == {
        "availability": "NOT_PUBLISHED",
        "source": "schwab",
        "reason_code": "INDEX_NO_EXECUTABLE_ORDER_BOOK",
    }
    assert response.json()["field_evidence"]["ask"] == {
        "availability": "NOT_PUBLISHED",
        "source": "schwab",
        "reason_code": "INDEX_NO_EXECUTABLE_ORDER_BOOK",
    }
    assert provider.requested_symbols == ["SPX"]


def test_quote_freshness_uses_configured_sixty_second_boundary() -> None:
    fresh_provider = StaticQuoteProvider(
        QuoteSnapshot(
            symbol="QQQ",
            provider="schwab",
            timestamp=NOW - timedelta(seconds=60),
        )
    )
    stale_provider = StaticQuoteProvider(
        QuoteSnapshot(
            symbol="QQQ",
            provider="schwab",
            timestamp=NOW - timedelta(seconds=60, microseconds=1),
        )
    )

    fresh = _client(fresh_provider).get("/api/v2/market/quote/QQQ").json()
    stale = _client(stale_provider).get("/api/v2/market/quote/QQQ").json()

    assert fresh["age_seconds"] == 60.0
    assert fresh["freshness"] == "FRESH"
    assert stale["age_seconds"] == 60.000001
    assert stale["freshness"] == "STALE"


def test_missing_quote_values_and_timestamp_remain_unavailable() -> None:
    provider = StaticQuoteProvider(QuoteSnapshot(symbol="SPY", provider="schwab"))

    response = _client(provider).get("/api/v2/market/quote/SPY")

    assert response.status_code == 200
    payload = response.json()
    assert payload["last"] is None
    assert payload["bid"] is None
    assert payload["ask"] is None
    assert payload["change_pct"] is None
    assert payload["volume"] is None
    assert payload["quote_timestamp"] is None
    assert payload["trade_timestamp"] is None
    assert payload["realtime"] is None
    assert payload["age_seconds"] is None
    assert payload["freshness"] == "UNAVAILABLE"
    assert payload["status"] == "UNAVAILABLE"
    assert payload["field_evidence"]["bid"]["availability"] == "UNAVAILABLE"
    assert payload["field_evidence"]["bid"]["reason_code"] == "SOURCE_FIELD_UNAVAILABLE"


def test_provider_failure_returns_sanitized_503() -> None:
    response = _client(FailingQuoteProvider()).get("/api/v2/market/quote/SPY")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {"status": "UNAVAILABLE", "symbol": "SPY"}
    }
    assert "do-not-leak" not in response.text


def test_unsupported_symbol_is_rejected_without_provider_call() -> None:
    provider = StaticQuoteProvider(QuoteSnapshot(symbol="SPY", provider="schwab"))

    response = _client(provider).get("/api/v2/market/quote/IWM")

    assert response.status_code == 404
    assert provider.requested_symbols == []


def test_create_app_wires_schwab_quote_provider_when_enabled(
    monkeypatch,
    tmp_path,
) -> None:
    provider = StaticQuoteProvider(
        QuoteSnapshot(
            symbol="SPY",
            resolved_symbol="SPY",
            provider="schwab",
            last=662.14,
            timestamp=datetime.now(timezone.utc),
        )
    )
    requested_providers: list[str] = []

    def build_provider(name: str):
        requested_providers.append(name)
        return provider

    monkeypatch.setattr(web, "build_quote_provider", build_provider)

    client = TestClient(
        web.create_app(
            database=tmp_path / "qx.db",
            cache_dir=tmp_path / "bars",
            configure_canonical_providers=True,
        )
    )
    response = client.get("/api/v2/market/quote/SPY")

    assert response.status_code == 200
    assert requested_providers == ["schwab"]


def test_create_app_disables_quote_provider_with_canonical_providers(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        web,
        "build_quote_provider",
        lambda name: (_ for _ in ()).throw(AssertionError(name)),
    )

    client = TestClient(
        web.create_app(
            database=tmp_path / "qx.db",
            cache_dir=tmp_path / "bars",
            configure_canonical_providers=False,
        )
    )

    response = client.get("/api/v2/market/quote/SPY")
    assert response.status_code == 503
