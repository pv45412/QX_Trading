from copy import deepcopy
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Self
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
import pandas as pd
import pytest
import requests
from starlette.types import Message, Scope

from qx.data.cache import _write_cached_bars
from qx.data.dashboard_refresh import DashboardRefresh
from qx.data.stock_refresh import StockRefresh
from qx.interfaces import web
from qx.market import ai_review as ai
from qx.market import stock_evidence as stock

NOW = datetime(2026, 9, 11, 14, tzinfo=timezone.utc)
GENERATION = "a" * 32


class StockClock(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> Self:
        return cls.fromisoformat((NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)).isoformat())


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    original = os.getenv

    def getenv(name: str, default: Any = None) -> Any:
        if name == "OPENAI_API_KEY":
            pytest.fail("Inspection read credentials")
        if name == "SCANNER_AI_ENABLED":
            return "0"
        return original(name, default)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Inspection invoked a provider, refresh, network or normalizing cache reader")

    monkeypatch.setattr(os, "getenv", getenv)
    monkeypatch.setattr(stock, "datetime", StockClock)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(requests, "post", forbidden)
    monkeypatch.setattr(web, "build_market_data_provider", forbidden)
    monkeypatch.setattr(web, "_read_cached_bars", forbidden)
    monkeypatch.setattr(StockRefresh, "run", forbidden)
    monkeypatch.setattr(StockRefresh, "reserve", forbidden)
    monkeypatch.setattr(DashboardRefresh, "active_cache", forbidden)


def write_bars(path: Path, frame: pd.DataFrame, **provenance: Any) -> None:
    frame = frame.copy()
    frame.attrs["provenance"] = {
        "schema_version": 1, "actual_source": "schwab", "fallback_used": False,
        "retrieved_at": (NOW - timedelta(minutes=1)).isoformat(),
        "last_bar_label": frame.index[-1].isoformat(), **provenance,
    }
    _write_cached_bars(path, frame, object())


@pytest.fixture
def generation(tmp_path: Path) -> tuple[Path, Path]:
    directory = tmp_path / "stock_refresh" / "sp100" / GENERATION
    directory.mkdir(parents=True)
    membership = b"symbol\nAAPL\nBRK.B\n"
    (directory / "symbols.csv").write_bytes(membership)
    (directory / "symbols.meta.json").write_text(json.dumps({
        "schema_version": 1, "sha256": sha256(membership).hexdigest(),
        "source": "fixture-list", "retrieved_at": (NOW - timedelta(hours=1)).isoformat(),
        "official": False, "effective_date": None,
    }))
    (directory.parent / "current.json").write_text(json.dumps({
        "generation": GENERATION, "finished_at": (NOW - timedelta(seconds=30)).isoformat(),
        "data_as_of": "2026-09-10",
    }))
    dates = ai._calendar(NOW.date()).index[-23:-1]
    for ticker in ("AAPL", "SPY", "BRK_B"):
        values = [100.0 + i * (2 if ticker != "SPY" else 0.5) + (-1) ** i for i in range(22)]
        frame = pd.DataFrame({"open": values, "close": values,
                              "high": [v + 2 for v in values], "low": [v - 2 for v in values],
                              "volume": [1000.0 + i for i in range(22)]}, index=dates)
        write_bars(directory / f"{ticker}_1y.csv", frame)
    return tmp_path / "bars", directory


def inspect(generation: tuple[Path, Path], now: datetime = NOW, symbol: str = "AAPL") -> dict[str, Any]:
    return stock.inspect_stock_evidence(symbol, "sp100", generation[0], now)


def api_request(app: FastAPI, path: str, *, body: dict[str, str] | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, Any]:
    async def request() -> tuple[int, Any]:
        messages: list[Message] = []
        scope: Scope = {"type": "http", "method": "GET" if body is None else "POST",
                        "path": path, "root_path": "", "query_string": b"", "scheme": "http",
                        "http_version": "1.1", "server": ("testserver", 80), "client": ("testclient", 1),
                        "headers": [(k.encode(), v.encode()) for k, v in
                                    {"content-type": "application/json", **(headers or {})}.items()]}

        async def receive() -> Message:
            return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b""}

        async def send(message: Message) -> None:
            messages.append(message)

        await app(scope, receive, send)
        status = int(next(message["status"] for message in messages if message["type"] == "http.response.start"))
        return status, json.loads(b"".join(message.get("body", b"") for message in messages))

    return asyncio.run(request())


def test_completed_prices_do_not_certify_membership(generation: tuple[Path, Path]) -> None:
    evidence = inspect(generation)
    facts = evidence["facts"]
    assert evidence["schema_version"] == "qx.stock-evidence.v1"
    assert evidence["mode"] == "inspection_only"
    assert evidence["validation"] == {"price_status": "verified_completed_daily", "live_eligible": False,
                                       "generation_supported": False, "issues": []}
    assert facts["publication"]["generation"] == GENERATION
    assert facts["membership"]["symbols"] == ["AAPL", "BRK.B"]
    assert facts["membership"]["selected_symbol_present"] is True
    assert facts["membership"]["provenance_status"] == "content_bound"
    assert facts["membership"]["official_membership"] == "unknown"
    assert facts["membership"]["official"] is False
    assert facts["membership"]["effective_date"] is None
    assert len(facts["input_digests"]) == 7
    assert all(facts["input_digests"].values())
    assert facts["sources"]["AAPL"]["provenance_verified"] is True
    left, right = facts["windows"]["AAPL"]["close"], facts["windows"]["SPY"]["close"]
    assert facts["bar_date"] == "2026-09-10"
    assert facts["return_1d"] == left[-1] / left[-2] - 1
    assert facts["excess_1d"] == left[-1] / left[-2] - right[-1] / right[-2]
    assert facts["rs_change"] == (left[-1] / right[-1]) / (left[0] / right[0]) - 1
    changes = [(left[i] / left[i - 1] - 1, right[i] / right[i - 1] - 1) for i in range(1, 22)]
    assert facts["rs_days"] == sum(a > b for a, b in changes)
    assert facts["down_days"] == sum(b < 0 for _, b in changes)
    assert facts["up_days"] == sum(a > 0 and b < 0 for a, b in changes)
    stock.validate_stock_evidence(evidence, generation[0], NOW)
    json.dumps(evidence, allow_nan=False)


def test_inspection_is_read_only_and_lease_is_not_identity(generation: tuple[Path, Path]) -> None:
    cache, directory = generation
    before = {p: p.read_bytes() for p in directory.parent.rglob("*") if p.is_file()}
    first = inspect(generation)
    second = inspect(generation, NOW + timedelta(seconds=20))
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["checked_at"] != second["checked_at"]
    assert {p: p.read_bytes() for p in directory.parent.rglob("*") if p.is_file()} == before
    assert not cache.exists()


def test_mutable_membership_and_prices_are_never_fallbacks(generation: tuple[Path, Path]) -> None:
    cache, directory = generation
    first = inspect(generation)
    cache.mkdir()
    (cache.parent / "sp100_symbols.csv").write_text("symbol\nMSFT\n")
    (cache / "AAPL_1y.csv").write_text("not frozen evidence")
    assert inspect(generation)["snapshot_id"] == first["snapshot_id"]
    (directory.parent / "current.json").unlink()
    missing = inspect(generation)
    assert missing["validation"]["price_status"] == "unavailable"
    assert missing["facts"]["windows"] == {}
    assert missing["facts"]["return_1d"] is None


@pytest.mark.parametrize("failure", ["missing", "empty", "duplicate", "alias", "extra_cell", "duplicate_header", "spy"])
def test_frozen_membership_is_required(generation: tuple[Path, Path], failure: str) -> None:
    path = generation[1] / "symbols.csv"
    contents = {"empty": "symbol\n", "duplicate": "symbol\nAAPL\nAAPL\n",
                "alias": "symbol\nAAPL\nBRK.B\nBRK-B\n", "extra_cell": "symbol\nAAPL,MSFT\n",
                "duplicate_header": "symbol,symbol\nAAPL,AAPL\n", "spy": "symbol\nAAPL\nSPY\n"}
    if failure == "missing":
        path.unlink()
    else:
        path.write_text(contents[failure])
    evidence = inspect(generation)
    assert evidence["validation"]["price_status"] == "unavailable"
    assert evidence["facts"]["bar_date"] is None


def test_exact_share_class_identity_and_absent_symbol(generation: tuple[Path, Path]) -> None:
    assert inspect(generation, symbol="BRK.B")["validation"]["price_status"] == "verified_completed_daily"
    for symbol in ("BRK-B", "MSFT"):
        evidence = inspect(generation, symbol=symbol)
        assert evidence["validation"]["price_status"] == "unavailable"
        assert evidence["facts"]["membership"]["selected_symbol_present"] is False
        assert evidence["facts"]["windows"] == {}


@pytest.mark.parametrize("failure", ["missing", "digest", "naive", "future", "duplicate", "official_claim",
                                   "bool_version", "float_version", "blank_source", "after_publication"])
def test_membership_metadata_cannot_certify(generation: tuple[Path, Path], failure: str) -> None:
    path = generation[1] / "symbols.meta.json"
    record = json.loads(path.read_text())
    if failure == "missing":
        path.unlink()
    elif failure == "duplicate":
        path.write_text(path.read_text().replace('"source":', '"source": "forged", "source":'))
    else:
        changes: dict[str, dict[str, Any]] = {"digest": {"sha256": "f" * 64}, "naive": {"retrieved_at": "2026-09-11T13:00:00"},
                   "future": {"retrieved_at": (NOW + timedelta(seconds=1)).isoformat()},
                   "bool_version": {"schema_version": True}, "float_version": {"schema_version": 1.0},
                   "blank_source": {"source": "   "},
                   "after_publication": {"retrieved_at": (NOW - timedelta(seconds=15)).isoformat()},
                   "official_claim": {"official": True, "effective_date": "2026-09-10"}}
        path.write_text(json.dumps({**record, **changes[failure]}))
    evidence = inspect(generation)
    member = evidence["facts"]["membership"]
    assert evidence["validation"]["price_status"] == "verified_completed_daily"
    assert member["provenance_status"] == ("content_bound" if failure == "official_claim" else "unknown")
    assert member["official_membership"] == "unknown"
    assert member["official"] is False
    assert member["effective_date"] is None


@pytest.mark.parametrize("failure", ["missing", "close_only", "nan", "inf", "zero", "negative_volume", "bool",
                                      "ohlc", "duplicate_date", "reverse", "missing_session", "intraday", "future",
                                      "timezone", "extra_unfinished", "duplicate_column", "extra_cell"])
def test_raw_bars_are_not_repaired(generation: tuple[Path, Path], failure: str) -> None:
    path = generation[1] / "AAPL_1y.csv"
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if failure == "missing":
        path.unlink()
    elif failure == "extra_cell":
        path.write_text(path.read_text().replace("1000.0\n", "1000.0,42\n"))
    else:
        if failure == "close_only":
            frame = frame[["close"]]
        elif failure in {"nan", "inf", "zero"}:
            frame.at[frame.index[0], "close"] = {"nan": float("nan"), "inf": float("inf"), "zero": 0}[failure]
        elif failure == "negative_volume":
            frame["volume"] = -1
        elif failure == "bool":
            frame["close"] = True
        elif failure == "ohlc":
            frame["high"] = frame["low"] - 1
        elif failure == "duplicate_date":
            frame.index = list(frame.index[:-1]) + [frame.index[-2]]
        elif failure == "reverse":
            frame = frame.iloc[::-1]
        elif failure == "missing_session":
            frame = frame.drop(frame.index[3])
        elif failure == "intraday":
            frame.index += pd.Timedelta(hours=1)
        elif failure == "future":
            frame.index = list(frame.index[:-1]) + [pd.Timestamp("2026-09-14")]
        elif failure == "timezone":
            frame.index = pd.DatetimeIndex(frame.index).tz_localize("UTC")
        elif failure == "extra_unfinished":
            extra = frame.iloc[-1:].copy()
            extra.index = pd.DatetimeIndex([NOW.date()])
            frame = pd.concat([frame, extra])
        else:
            frame = pd.concat([frame, frame[["close"]]], axis=1)
        write_bars(path, frame)
    evidence = inspect(generation)
    assert evidence["validation"]["price_status"] == "unavailable"
    assert evidence["facts"]["return_1d"] is None
    assert "AAPL" not in evidence["facts"]["windows"]
    stock.validate_stock_evidence(evidence, generation[0], NOW)
    json.dumps(evidence, allow_nan=False)


@pytest.mark.parametrize("failure", ["missing", "digest", "unknown", "naive", "future", "early", "label", "fallback", "duplicate"])
def test_price_provenance_is_separate_from_price_metrics(generation: tuple[Path, Path], failure: str) -> None:
    path = generation[1] / "AAPL_1y.meta.json"
    record = json.loads(path.read_text())
    if failure == "missing":
        path.unlink()
    elif failure == "duplicate":
        path.write_text(path.read_text().replace('"actual_source":', '"actual_source": "yfinance", "actual_source":'))
    else:
        if failure == "digest":
            record["sha256"] = "f" * 64
        else:
            changes = {"unknown": {"actual_source": "unknown"}, "naive": {"retrieved_at": "2026-09-11T13:00:00"},
                       "future": {"retrieved_at": NOW.isoformat()}, "early": {"retrieved_at": "2026-09-10T20:29:00+00:00"},
                       "label": {"last_bar_label": "2026-09-09T00:00:00"}, "fallback": {"fallback_used": "false"}}
            record["provenance"].update(changes[failure])
        path.write_text(json.dumps(record))
    evidence = inspect(generation)
    assert evidence["validation"]["price_status"] == "unverified"
    assert evidence["facts"]["return_1d"] is not None
    assert evidence["facts"]["sources"]["AAPL"]["provenance_verified"] is False
    stock.validate_stock_evidence(evidence, generation[0], NOW)


@pytest.mark.parametrize("change", [{"generation": "../../bars"}, {"generation": "b" * 32},
                                    {"finished_at": "2026-09-11T14:00:00"},
                                    {"finished_at": (NOW + timedelta(seconds=1)).isoformat()},
                                    {"finished_at": "2026-09-10T20:29:00+00:00"},
                                    {"data_as_of": "2026-09-09"}, {"data_as_of": "2026-09-12"},
                                    {"extra": "unbound"}])
def test_publication_is_validated(generation: tuple[Path, Path], change: dict[str, str]) -> None:
    path = generation[1].parent / "current.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **change}))
    assert inspect(generation)["validation"]["price_status"] == "unavailable"


@pytest.mark.parametrize("target", ["current.json", "symbols.csv", "symbols.meta.json", "AAPL_1y.csv", "SPY_1y.meta.json"])
def test_read_races_do_not_publish_mixed_evidence(generation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
                                                target: str) -> None:
    original = Path.read_bytes
    counts: dict[Path, int] = {}

    def read(path: Path) -> bytes:
        content = original(path)
        counts[path] = counts.get(path, 0) + 1
        if path.name == target and counts[path] == 2:
            return content + b"\n"
        return content

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ai.ReviewUnavailable, match="changed during"):
        inspect(generation)


@pytest.mark.parametrize("target", ["symbols.csv", "symbols.meta.json", "AAPL_1y.csv", "SPY_1y.meta.json"])
def test_content_changes_invalidate_id_and_lease(generation: tuple[Path, Path], target: str) -> None:
    evidence = inspect(generation)
    path = generation[1] / target
    path.write_bytes(path.read_bytes() + b"\n")
    assert inspect(generation)["snapshot_id"] != evidence["snapshot_id"]
    with pytest.raises(ai.ReviewUnavailable):
        stock.validate_stock_evidence(evidence, generation[0], NOW)


def test_generation_identity_and_session_rollover(generation: tuple[Path, Path]) -> None:
    first = inspect(generation)
    directory = generation[1]
    replacement = directory.parent / ("b" * 32)
    replacement.mkdir()
    for path in directory.iterdir():
        (replacement / path.name).write_bytes(path.read_bytes())
    pointer = directory.parent / "current.json"
    pointer.write_text(json.dumps({**json.loads(pointer.read_text()), "generation": replacement.name}))
    assert inspect(generation)["snapshot_id"] != first["snapshot_id"]
    before = datetime(2026, 9, 11, 20, 29, tzinfo=timezone.utc)
    fresh = inspect(generation, before)
    with pytest.raises(ai.ReviewUnavailable):
        stock.validate_stock_evidence(fresh, generation[0], before + timedelta(minutes=2))
    assert inspect(generation, before + timedelta(minutes=2))["validation"]["price_status"] == "historical"


@pytest.mark.parametrize("mutation", ["metric", "official", "effective", "eligibility", "limitations", "schema", "extra", "window", "source"])
def test_rehashed_claims_are_not_trusted(generation: tuple[Path, Path], mutation: str) -> None:
    evidence = deepcopy(inspect(generation))
    if mutation == "metric":
        evidence["facts"]["rs_days"] = True
    elif mutation == "official":
        evidence["facts"]["membership"]["official"] = True
    elif mutation == "effective":
        evidence["facts"]["membership"]["effective_date"] = "2026-09-10"
    elif mutation == "eligibility":
        evidence["validation"]["live_eligible"] = True
    elif mutation == "limitations":
        evidence["limitations"] = []
    elif mutation == "schema":
        evidence["schema_version"] = ai.SCHEMA_VERSION
    elif mutation == "extra":
        evidence["recommendation"] = "invented output"
    elif mutation == "window":
        evidence["facts"]["windows"]["AAPL"]["close"][0] += 1
    else:
        evidence["facts"]["sources"]["AAPL"]["fallback_used"] = True
    evidence["snapshot_id"] = stock._snapshot_id(evidence)
    with pytest.raises(ai.ReviewUnavailable):
        stock.validate_stock_evidence(evidence, generation[0], NOW)


@pytest.mark.parametrize("failure", ["expired", "future", "naive", "long"])
def test_inspection_lease(generation: tuple[Path, Path], failure: str) -> None:
    evidence = inspect(generation)
    now = NOW
    if failure == "expired":
        now += timedelta(minutes=5)
    elif failure == "future":
        evidence["checked_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif failure == "naive":
        evidence["expires_at"] = "2026-09-11T14:05:00"
    else:
        evidence["expires_at"] = (NOW + timedelta(hours=1)).isoformat()
    with pytest.raises(ai.ReviewUnavailable):
        stock.validate_stock_evidence(evidence, generation[0], now)


@pytest.mark.parametrize("symbol", ["XLK", "SPY", "QQQ", "DIA", "ES=F", "/ES", "AAPL260918C00100000", "../AAPL"])
def test_unsupported_instruments(generation: tuple[Path, Path], symbol: str) -> None:
    with pytest.raises(stock.UnsupportedStockEvidence):
        inspect(generation, symbol=symbol)


def test_stock_contract_cannot_enter_etf_generation(generation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = inspect(generation)
    with pytest.raises(ai.ReviewUnavailable):
        ai.validate_rs_evidence(evidence, NOW, require_live=False)
    service = ai.AIReviewer()
    # Simulate an enabled service without changing environment or supplying credentials.
    monkeypatch.setattr(service, "require_enabled", lambda: {"model": "unused-fixture-model"})
    with pytest.raises(ai.ReviewUnavailable):
        service.review(evidence)


def test_stock_api_schema_and_unsupported_state(generation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    app = web.create_app(cache_dir=generation[0])
    _, status = api_request(app, "/api/ai/status")
    assert status["enabled"] is False
    assert status["schema_version"] == "qx.rs-review.v2"
    assert status["contracts"]["stock"]["generation_supported"] is False
    for kind in ("futures", "options"):
        assert status["contracts"][kind]["schema_version"] is None
        assert status["contracts"][kind]["inspection_supported"] is False
    code, result = api_request(app, "/api/ai/stocks/sp100/evidence/aapl")
    assert code == 200
    assert result == inspect(generation)
    _, schema = api_request(app, "/openapi.json")
    response = schema["paths"]["/api/ai/stocks/{universe}/evidence/{symbol}"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith("/StockEvidence")
    assert schema["components"]["schemas"]["StockEvidence"]["additionalProperties"] is False
    post_responses = schema["paths"]["/api/ai/stocks/{universe}/review/{symbol}"]["post"]["responses"]
    assert "200" not in post_responses
    assert "unsupported" in post_responses["422"]["description"]
    assert api_request(app, "/api/ai/stocks/russell_2000/evidence/AAPL")[0] == 422
    code, bad_symbol = api_request(app, "/api/ai/stocks/sp100/evidence/ES=F")
    assert code == 422
    assert bad_symbol["detail"]["code"] == "unsupported_stock_evidence"
    fail = Mock(side_effect=AssertionError("Unsupported generation inspected bytes or service configuration"))
    monkeypatch.setattr(web, "inspect_stock_evidence", fail)
    monkeypatch.setattr(ai.AIReviewer, "require_enabled", fail)
    url = "/api/ai/stocks/sp100/review/AAPL"
    body = {"snapshot_id": result["snapshot_id"]}
    assert api_request(app, url, body=body)[0] == 403
    assert api_request(app, url, body=body, headers={"x-qx-ai": "1", "sec-fetch-site": "cross-site"})[0] == 403
    code, unsupported = api_request(app, url, body=body, headers={"x-qx-ai": "1"})
    assert code == 422
    assert unsupported["detail"]["code"] == "stock_generation_unsupported"
    fail.assert_not_called()


def test_api_race_returns_conflict(generation: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "inspect_stock_evidence", Mock(side_effect=ai.ReviewUnavailable("changed")))
    app = web.create_app(cache_dir=generation[0])
    route = next(route for route in app.routes if getattr(route, "path", "") == "/api/ai/stocks/{universe}/evidence/{symbol}")
    with pytest.raises(HTTPException) as exc:
        route.endpoint("sp100", "AAPL")  # type: ignore[attr-defined]
    assert exc.value.status_code == 409
