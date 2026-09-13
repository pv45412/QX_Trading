"""Holdings navigation is disk-only; explicit refreshes use isolated provider fixtures."""

from copy import deepcopy
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from qx.data import holdings
from qx.interfaces import web


@pytest.fixture(autouse=True)
def block_external_feeds(monkeypatch):
    # Windows creates an internal loopback socket pair when the event loop starts.
    loop = asyncio.new_event_loop()
    blocked = Mock(side_effect=AssertionError("External feeds/models are forbidden"))
    for target, name in (
        (socket.socket, "connect"), (socket, "create_connection"),
        (requests.Session, "request"),
        (holdings.yf, "Ticker"), (holdings.yf, "download"),
        (web, "build_market_data_provider"), (web, "_schwab_client"),
        (web, "fetch_top_movers"), (web.AIReviewer, "review"),
    ):
        monkeypatch.setattr(target, name, blocked)
    try:
        from curl_cffi.requests import Session as CurlSession
    except ImportError:
        pass
    else:
        monkeypatch.setattr(CurlSession, "request", blocked)
    provider = holdings.top_holdings
    provider.cache_clear()
    yield loop
    loop.close()
    provider.cache_clear()
    blocked.assert_not_called()


@pytest.fixture
def payload():
    return {
        "symbol": "XLK", "source": "Yahoo Finance fund data", "holdings_as_of": None,
        "retrieved_at": "2025-01-01T08:00:00-05:00",
        "provenance": {"requested_symbol": "XLK", "provider": "Yahoo Finance fund data"},
        "rows": [{"symbol": "AAPL", "name": "Apple", "weight": .2}],
    }


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache" / "holdings"


@pytest.fixture
def client(tmp_path, block_external_feeds):
    app = web.create_app(tmp_path / "missing.db", tmp_path / "cache" / "bars")

    def request(method, path, headers=None):
        async def run():
            messages = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await app({
                "type": "http", "http_version": "1.1", "scheme": "http",
                "method": method, "path": path, "query_string": b"",
                "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
                "server": ("testserver", 80), "client": ("testclient", 50000),
            }, receive, send)
            body = b"".join(message.get("body", b"") for message in messages).decode()
            status = next(message["status"] for message in messages if message["type"] == "http.response.start")
            return SimpleNamespace(status_code=status, text=body, json=lambda: json.loads(body))

        return block_external_feeds.run_until_complete(run())

    return SimpleNamespace(get=lambda path, **kw: request("GET", path, **kw),
                           post=lambda path, **kw: request("POST", path, **kw))


def save(cache_dir, payload):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "XLK.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def snapshot(path):
    return path.read_bytes(), path.stat().st_mtime_ns


def test_saved_loader_and_repeated_get_preserve_identity_time_provenance_and_disk(
    monkeypatch, client, cache_dir, payload,
):
    path = save(cache_dir, payload)
    before = snapshot(path)
    provider = Mock(side_effect=AssertionError("Passive provider call"))
    write = Mock(side_effect=AssertionError("Passive cache write"))
    mkdir = Mock(side_effect=AssertionError("Passive directory write"))
    monkeypatch.setattr(holdings, "top_holdings", provider)
    monkeypatch.setattr(holdings, "_fetch_top_holdings", provider)
    monkeypatch.setattr(holdings, "_atomic_write", write)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    saved = holdings.saved_top_holdings("XLK", cache_dir)
    assert all(saved[key] == value for key, value in payload.items())
    for _ in range(2):
        response = client.get("/api/rotation/xlk/holdings")
        assert response.status_code == 200
        result = response.json()
        for key in ("symbol", "source", "retrieved_at", "holdings_as_of", "provenance"):
            assert result[key] == payload[key]
        assert result["rows"] == [{**payload["rows"][0], "analytics": None}]
        assert result["holdings_status"] == "SAVED_UNVERIFIED"
        assert result["refresh_error"] is None
        assert result["analytics_coverage"] == 0
    assert snapshot(path) == before
    provider.assert_not_called()
    write.assert_not_called()
    mkdir.assert_not_called()


def test_missing_get_does_not_create_cache_or_fetch(client, cache_dir):
    response = client.get("/api/rotation/XLK/holdings")
    assert response.status_code == 404
    assert "saved" in response.json()["detail"]
    assert not cache_dir.parent.exists()


@pytest.mark.parametrize("corruption", [
    "json", "wrong_fund", "empty", "duplicate", "overweight", "nan", "boolean",
    "naive_time", "future_time", "missing_time", "source", "name", "row", "effective_date",
])
def test_incompatible_saved_holdings_fail_closed(client, cache_dir, payload, corruption):
    bad = deepcopy(payload)
    if corruption == "wrong_fund":
        bad["symbol"] = "XLE"
    elif corruption == "empty":
        bad["rows"] = []
    elif corruption == "duplicate":
        bad["rows"] *= 2
    elif corruption == "overweight":
        bad["rows"] = [{"symbol": "AAPL", "weight": .8}, {"symbol": "MSFT", "weight": .8}]
    elif corruption in ("nan", "boolean"):
        bad["rows"][0]["weight"] = float("nan") if corruption == "nan" else True
    elif corruption == "naive_time":
        bad["retrieved_at"] = "2025-01-01T08:00:00"
    elif corruption == "future_time":
        bad["retrieved_at"] = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    elif corruption == "missing_time":
        del bad["retrieved_at"]
    elif corruption == "source":
        bad["source"] = ""
    elif corruption == "name":
        bad["rows"][0]["name"] = {}
    elif corruption == "row":
        bad["rows"] = [None]
    elif corruption == "effective_date":
        bad["holdings_as_of"] = {}
    path = save(cache_dir, bad)
    if corruption == "json":
        path.write_text("{invalid", encoding="utf-8")
    before = snapshot(path)
    response = client.get("/api/rotation/XLK/holdings")
    assert response.status_code == 503
    assert "rows" not in response.json()
    assert "AAPL" not in response.text
    assert str(cache_dir) not in response.text
    assert snapshot(path) == before


@pytest.mark.parametrize("symbol", ["AAPL", "NOTAFUND", "XLK.json"])
def test_unsupported_funds_are_rejected_before_cache_or_provider(client, symbol):
    for method, suffix in (("get", ""), ("post", "/refresh")):
        response = getattr(client, method)(
            f"/api/rotation/{symbol}/holdings{suffix}", headers={"X-Scanner-Refresh": "1"},
        )
        assert response.status_code == 404


@pytest.mark.parametrize("headers", [
    {}, {"X-Scanner-Refresh": "0"},
    {"X-Scanner-Refresh": "1", "Sec-Fetch-Site": "cross-site"},
])
def test_refresh_requires_existing_same_origin_custom_header_guard(client, headers):
    assert client.post("/api/rotation/XLK/holdings/refresh", headers=headers).status_code == 403


def test_explicit_post_fetches_once_and_subsequent_get_only_reads(
    monkeypatch, client, cache_dir,
):
    ticker = Mock(return_value=SimpleNamespace(funds_data=SimpleNamespace(
        top_holdings=pd.DataFrame({"Name": ["Apple"], "Holding Percent": [.2]}, index=["AAPL"]),
    )))
    monkeypatch.setattr(holdings.yf, "Ticker", ticker)
    assert client.get("/api/rotation/XLK/holdings").status_code == 404
    ticker.assert_not_called()
    response = client.post("/api/rotation/xlk/holdings/refresh", headers={"X-Scanner-Refresh": "1"})
    assert response.status_code == 200
    result = response.json()
    assert result["holdings_status"] == "REFRESHED"
    assert result["holdings_as_of"] is None
    path = cache_dir / "XLK.json"
    before = snapshot(path)
    assert "holdings_status" not in json.loads(path.read_text(encoding="utf-8"))
    saved = client.get("/api/rotation/XLK/holdings").json()
    assert saved["retrieved_at"] == result["retrieved_at"]
    assert saved["rows"] == result["rows"]
    assert saved["holdings_as_of"] is None
    assert saved["refresh_error"] is None
    assert snapshot(path) == before
    ticker.assert_called_once_with("XLK")


def test_each_explicit_post_bypasses_populated_same_hour_lru(monkeypatch, client):
    ticker = Mock(return_value=SimpleNamespace(funds_data=SimpleNamespace(
        top_holdings=pd.DataFrame({"Name": ["Apple"], "Holding Percent": [.2]}, index=["AAPL"]),
    )))
    monkeypatch.setattr(holdings.yf, "Ticker", ticker)
    bucket = int(web.time.time() // 3600)
    holdings.top_holdings("XLK", bucket)
    holdings.top_holdings("XLK", bucket)
    assert ticker.call_count == 1
    for expected in (2, 3):
        response = client.post("/api/rotation/XLK/holdings/refresh", headers={"X-Scanner-Refresh": "1"})
        assert response.status_code == 200
        assert response.json()["holdings_as_of"] is None
        assert ticker.call_count == expected
        assert client.get("/api/rotation/XLK/holdings").status_code == 200
        assert ticker.call_count == expected


@pytest.mark.parametrize("invalid_result", [False, True])
def test_failed_refresh_keeps_previous_rows_timestamp_and_file(
    monkeypatch, client, cache_dir, payload, invalid_result,
):
    path = save(cache_dir, payload)
    before = snapshot(path)
    provider = Mock(return_value={**payload, "symbol": "XLE"}) if invalid_result else Mock(
        side_effect=RuntimeError("private provider detail"),
    )
    monkeypatch.setattr(holdings, "_fetch_top_holdings", provider)
    first = client.get("/api/rotation/XLK/holdings").json()
    provider.assert_not_called()
    response = client.post("/api/rotation/XLK/holdings/refresh", headers={"X-Scanner-Refresh": "1"})
    assert response.status_code == 200
    result = response.json()
    for key in ("rows", "retrieved_at", "holdings_as_of", "provenance", "source"):
        assert result[key] == first[key]
    assert result["stale_holdings"] is True
    assert "refresh failed" in result["refresh_error"]
    assert "private provider detail" not in response.text
    assert snapshot(path) == before
    assert client.get("/api/rotation/XLK/holdings").json()["refresh_error"] is None
    assert provider.call_count == 1


@pytest.mark.parametrize("saved_symbol", [None, "XLE"])
def test_failed_refresh_without_compatible_cache_is_honest_error(
    monkeypatch, client, cache_dir, payload, saved_symbol,
):
    if saved_symbol:
        save(cache_dir, {**payload, "symbol": saved_symbol})
    provider = Mock(side_effect=RuntimeError("private provider detail"))
    monkeypatch.setattr(holdings, "_fetch_top_holdings", provider)
    response = client.post("/api/rotation/XLK/holdings/refresh", headers={"X-Scanner-Refresh": "1"})
    assert response.status_code == 503
    assert "No compatible saved holdings" in response.json()["detail"]
    assert "private provider detail" not in response.text
    assert "rows" not in response.json()
    assert provider.call_count == 1


def test_refresh_save_failure_does_not_replace_previous_file(
    monkeypatch, client, cache_dir, payload,
):
    path = save(cache_dir, payload)
    before = snapshot(path)
    monkeypatch.setattr(holdings, "_fetch_top_holdings", Mock(return_value={
        **payload, "rows": [{"symbol": "MSFT", "name": "Microsoft", "weight": .3}],
    }))
    monkeypatch.setattr(holdings, "_atomic_write", Mock(side_effect=OSError("disk full")))
    result = client.post("/api/rotation/XLK/holdings/refresh", headers={"X-Scanner-Refresh": "1"}).json()
    assert result["holdings_status"] == "REFRESHED_UNSAVED"
    assert result["rows"][0]["symbol"] == "MSFT"
    assert "could not be saved" in result["cache_warning"]
    assert snapshot(path) == before
