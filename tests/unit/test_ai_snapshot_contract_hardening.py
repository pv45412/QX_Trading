"""Deterministic contract tests; real credentials and network transports are forbidden."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
import pandas as pd
import pandas_market_calendars as mcal
import pytest
import requests
from starlette.requests import Request
from streamlit.testing.v1 import AppTest

from qx.interfaces import web
from qx.market import ai_review as ai
from qx.ui import ai_evidence as bridge


NOW = datetime(2026, 9, 11, 14, tzinfo=timezone.utc)


class ContractClock(datetime):
    current = NOW

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    config = {"SCANNER_AI_ENABLED": "", "SCANNER_AI_MODEL": "", "OPENAI_API_KEY": "unit-test-token"}
    reads = []

    def getenv(name, default=None):
        if name == "OPENAI_API_KEY":
            reads.append(name)
        return config.get(name, default)

    monkeypatch.setattr(ai.os, "getenv", getenv)
    monkeypatch.setattr(ContractClock, "current", NOW)
    monkeypatch.setattr(ai, "datetime", ContractClock)
    monkeypatch.setattr(bridge, "datetime", ContractClock)
    forbidden = Mock(side_effect=AssertionError("Unexpected transport/provider/refresh call"))
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(requests, "post", forbidden)
    monkeypatch.setattr(web, "build_market_data_provider", forbidden)
    monkeypatch.setattr(web, "_schwab_client", forbidden)
    monkeypatch.setattr(web.DashboardRefresh, "run", forbidden)
    return config, reads, forbidden


@pytest.fixture
def bars():
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-05-01", end_date="2026-09-10").index
    return pd.DataFrame({"close": [100.0 + n / 10 for n in range(len(dates))]}, index=dates)


def write_cache(path, frame, **overrides):
    content = frame.to_csv().encode()
    path.write_bytes(content)
    source = {"schema_version": 1, "actual_source": "schwab", "fallback_used": False,
              "retrieved_at": (NOW - timedelta(minutes=1)).isoformat(),
              "last_bar_label": frame.index[-1].isoformat() if len(frame) else None}
    source.update(overrides)
    path.with_suffix(".meta.json").write_text(json.dumps({"sha256": sha256(content).hexdigest(), "provenance": source}))


@pytest.fixture
def cache(tmp_path, bars):
    for ticker in ("XLK", "SPY", "XLE"):
        write_cache(tmp_path / f"{ticker}_1y.csv", bars)
    return tmp_path


def endpoint(cache, path):
    app = web.create_app(cache / "unused.db", cache)
    return next(route.endpoint for route in app.routes if route.path == path)


def request(headers=None):
    return Request({"type": "http", "headers": headers if headers is not None else [(b"x-qx-ai", b"1")]})


def enable(isolated):
    config, _, _ = isolated
    config.update(SCANNER_AI_ENABLED="1", SCANNER_AI_MODEL="unit-test-model")


def selection(evidence):
    return {"snapshot_id": evidence["snapshot_id"], "observations": ["relative_strength"], "checks": ["events"]}


def provider_response(evidence, content=None):
    content = content if content is not None else [{"type": "output_text", "text": json.dumps(selection(evidence))}]
    return SimpleNamespace(status_code=200, json=lambda: {"status": "completed", "output": [{"type": "message", "content": content}]})


def test_version_identity_and_frontend_fields_are_deterministic(cache):
    evidence = ai.build_rs_evidence("XLK", cache)
    assert evidence["schema_version"] == "qx.rs-review.v2"
    assert len(evidence["snapshot_id"]) == 64
    assert evidence["snapshot_id"] == ai.build_rs_evidence("XLK", cache, NOW + timedelta(seconds=10))["snapshot_id"]
    assert evidence["snapshot_id"] != ai.build_rs_evidence("XLE", cache)["snapshot_id"]
    assert evidence["facts"]["universe"] == ["XLK"]
    assert evidence["facts"]["benchmark"] == "SPY"
    assert len(evidence["facts"]["windows"]["XLK"]["dates"]) == 22
    assert evidence["validation"] == {"status": "verified_completed_daily", "live_eligible": True, "issues": []}
    assert all(key in evidence for key in ("facts", "observations", "checks", "limitations", "checked_at", "expires_at"))


@pytest.mark.parametrize("change", ["value", "source", "retrieved", "fallback", "older_bytes"])
def test_identity_binds_source_and_exact_input_bytes(cache, bars, change):
    first = ai.build_rs_evidence("XLK", cache)
    overrides = {}
    if change == "value":
        bars.iloc[-1, 0] += 1
    elif change == "older_bytes":
        bars.iloc[0, 0] += 1
    elif change == "source":
        overrides["actual_source"] = "yfinance"
    elif change == "retrieved":
        overrides["retrieved_at"] = NOW.isoformat()
    else:
        overrides["fallback_used"] = True
    write_cache(cache / "XLK_1y.csv", bars, **overrides)
    assert ai.build_rs_evidence("XLK", cache)["snapshot_id"] != first["snapshot_id"]


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schema_version="qx.rs-review.v1"),
    lambda data: data.update(prompt="unbound extra data"),
    lambda data: data["facts"].update(universe=["XLE"]),
    lambda data: data["facts"].update(benchmark="QQQ"),
    lambda data: data["facts"].update(bar_date="2026-09-09"),
    lambda data: data["facts"].pop("return_1d"),
    lambda data: data["facts"].update(rs_days=True),
    lambda data: data["facts"].update(return_1d=float("nan")),
    lambda data: data["facts"].update(rs_change=float("inf")),
    lambda data: data["facts"]["windows"]["XLK"]["dates"].pop(),
    lambda data: data["facts"]["sources"].pop("SPY"),
    lambda data: data["facts"]["sources"]["SPY"].update(retrieved_at=None),
    lambda data: data["observations"][0].update(text="invented market fact"),
    lambda data: data["checks"].update(events="invented check"),
    lambda data: data["limitations"].clear(),
    lambda data: data["validation"].update(live_eligible=False),
])
def test_invalid_contract_never_reads_credentials_or_calls_transport(cache, isolated, mutation):
    enable(isolated)
    evidence = ai.build_rs_evidence("XLK", cache)
    mutation(evidence)
    with pytest.raises(ai.ReviewUnavailable):
        ai.AIReviewer().review(evidence)
    assert isolated[1] == []
    isolated[2].assert_not_called()


@pytest.mark.parametrize("mutation", [
    lambda data: data["facts"].update(excess_1d=0.7),
    lambda data: data["facts"]["sources"]["SPY"].update(retrieved_at="2026-09-11T13:00:00"),
    lambda data: data["facts"]["sources"]["SPY"].update(retrieved_at="2099-01-01T00:00:00+00:00"),
    lambda data: data["facts"]["sources"]["SPY"].update(fallback_used="false"),
    lambda data: data["facts"].update(universe=["XLK", "XLE"]),
    lambda data: data["observations"][0].update(text="invented text"),
])
def test_rehashing_bad_semantics_does_not_bypass_validation(cache, isolated, mutation):
    enable(isolated)
    evidence = ai.build_rs_evidence("XLK", cache)
    mutation(evidence)
    evidence["snapshot_id"] = ai._snapshot_identity(evidence)
    with pytest.raises(ai.ReviewUnavailable):
        ai.AIReviewer().review(evidence)
    assert isolated[1] == []


@pytest.mark.parametrize("failure", ["missing_file", "missing_close", "nan", "inf", "zero", "negative",
                                      "duplicate", "reversed", "missing_date", "nat", "intraday", "future", "only_21"])
def test_raw_cache_is_not_silently_repaired(cache, bars, failure, isolated):
    path = cache / "XLK_1y.csv"
    if failure == "missing_file":
        path.unlink()
    else:
        if failure == "missing_close":
            bars = bars.rename(columns={"close": "other"})
        elif failure in {"nan", "inf", "zero", "negative"}:
            bars.iloc[-3, 0] = {"nan": float("nan"), "inf": float("inf"), "zero": 0, "negative": -1}[failure]
        elif failure == "duplicate":
            bars = pd.concat([bars, bars.iloc[-1:]])
        elif failure == "reversed":
            bars = bars.iloc[::-1]
        elif failure == "missing_date":
            bars = bars.drop(bars.index[-3])
        elif failure == "nat":
            bars.index = list(bars.index[:-1]) + [pd.NaT]
        elif failure == "intraday":
            bars.index = bars.index + pd.Timedelta(hours=12)
        elif failure == "future":
            bars.index = list(bars.index[:-1]) + [pd.Timestamp("2026-09-14")]
        else:
            bars = bars.iloc[-21:]
        write_cache(path, bars)
    inspected = ai.inspect_rs_evidence("XLK", cache)
    assert inspected["validation"]["status"] == "unavailable"
    assert not inspected["validation"]["live_eligible"]
    assert inspected["facts"]["return_1d"] is None
    assert inspected["observations"] == []
    assert inspected["expires_at"] == inspected["checked_at"]
    json.dumps(inspected, allow_nan=False)
    ai.validate_rs_evidence(inspected, require_live=False)
    with pytest.raises(ai.ReviewUnavailable):
        ai.build_rs_evidence("XLK", cache)
    isolated[2].assert_not_called()


@pytest.mark.parametrize("failure", ["missing_meta", "digest", "unknown", "naive", "future", "too_early", "missing_label", "wrong_label", "fallback_type"])
def test_unverified_source_remains_inspectable_but_never_live(cache, failure, isolated):
    metadata_path = cache / "XLK_1y.meta.json"
    metadata = json.loads(metadata_path.read_text())
    changes = {"unknown": {"actual_source": "unknown"}, "naive": {"retrieved_at": "2026-09-11T13:59:00"},
               "future": {"retrieved_at": (NOW + timedelta(seconds=1)).isoformat()},
               "too_early": {"retrieved_at": "2026-09-10T20:29:00+00:00"},
               "missing_label": {"last_bar_label": None}, "wrong_label": {"last_bar_label": "2026-09-09T00:00:00"},
               "fallback_type": {"fallback_used": "false"}}
    if failure == "missing_meta":
        metadata_path.unlink()
    else:
        if failure == "digest":
            metadata["sha256"] = "f" * 64
        else:
            metadata["provenance"].update(changes[failure])
        metadata_path.write_text(json.dumps(metadata))
    inspected = ai.inspect_rs_evidence("XLK", cache)
    assert inspected["validation"]["status"] == "unverified"
    assert inspected["facts"]["bar_date"] == "2026-09-10"
    assert all(row["text"].startswith("Historical/unverified") for row in inspected["observations"])
    ai.validate_rs_evidence(inspected, require_live=False)
    enable(isolated)
    with pytest.raises(ai.ReviewUnavailable):
        ai.AIReviewer().review(inspected)
    assert isolated[1] == []


def test_historical_and_mixed_windows_are_explicit(cache, bars):
    write_cache(cache / "XLK_1y.csv", bars.iloc[:-1])
    mixed = ai.inspect_rs_evidence("XLK", cache)
    assert mixed["validation"]["status"] == "unavailable"
    assert mixed["facts"]["windows"]["XLK"]["dates"][-1] == "2026-09-09"
    write_cache(cache / "SPY_1y.csv", bars.iloc[:-1])
    historical = ai.inspect_rs_evidence("XLK", cache)
    assert historical["validation"]["status"] == "historical"
    assert historical["facts"]["bar_date"] == "2026-09-09"
    ai.validate_rs_evidence(historical, require_live=False)
    with pytest.raises(ai.ReviewUnavailable):
        ai.validate_rs_evidence(historical)


@pytest.mark.parametrize("change", ["expired", "future_check", "naive_check", "naive_expiry", "long_lease"])
def test_lease_validation_before_credentials(cache, isolated, change):
    evidence = ai.build_rs_evidence("XLK", cache)
    if change == "expired":
        ContractClock.current = NOW + timedelta(minutes=5)
    elif change == "future_check":
        evidence["checked_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == "naive_check":
        evidence["checked_at"] = NOW.replace(tzinfo=None).isoformat()
    elif change == "naive_expiry":
        evidence["expires_at"] = (NOW + timedelta(minutes=5)).replace(tzinfo=None).isoformat()
    else:
        evidence["expires_at"] = (NOW + timedelta(hours=1)).isoformat()
    enable(isolated)
    with pytest.raises(ai.ReviewUnavailable):
        ai.AIReviewer().review(evidence)
    assert isolated[1] == []


def test_session_rollover_invalidates_even_unexpired_lease(cache):
    before_close = datetime(2026, 9, 11, 20, 29, tzinfo=timezone.utc)
    evidence = ai.build_rs_evidence("XLK", cache, before_close)
    for live in (False, True):
        with pytest.raises(ai.ReviewUnavailable):
            ai.validate_rs_evidence(evidence, before_close + timedelta(minutes=2), require_live=live)


@pytest.mark.parametrize("enabled,model", [(None, "unit-test-model"), ("0", "unit-test-model"),
                                           ("true", "unit-test-model"), ("1", ""), ("1", "bad model")])
def test_disabled_or_unconfigured_post_short_circuits_all_work(cache, isolated, monkeypatch, enabled, model):
    isolated[0].update(SCANNER_AI_ENABLED=enabled, SCANNER_AI_MODEL=model)
    monkeypatch.setattr(web, "build_rs_evidence", isolated[2])
    post = endpoint(cache, "/api/ai/review/{symbol}")
    with pytest.raises(HTTPException) as exc:
        post("XLK", web.AIReviewRequest(snapshot_id="a" * 64), request())
    assert exc.value.status_code == 503
    assert isolated[1] == []
    isolated[2].assert_not_called()


def test_status_and_get_inspection_are_read_only_even_when_enabled(cache, isolated):
    enable(isolated)
    status = endpoint(cache, "/api/ai/status")()
    evidence = endpoint(cache, "/api/ai/evidence/{symbol}")("xlk")
    assert status["credentials_verified"] is False
    assert evidence["facts"]["bar_date"] == "2026-09-10"
    assert isolated[1] == []
    isolated[2].assert_not_called()


@pytest.mark.parametrize("headers", [[], [(b"x-qx-ai", b"0")], [(b"x-qx-ai", b"1"), (b"sec-fetch-site", b"cross-site")]])
def test_post_requires_explicit_request_header(cache, isolated, headers):
    enable(isolated)
    post = endpoint(cache, "/api/ai/review/{symbol}")
    with pytest.raises(HTTPException) as exc:
        post("XLK", web.AIReviewRequest(snapshot_id="a" * 64), request(headers))
    assert exc.value.status_code == 403
    assert isolated[1] == []


def test_mocked_transport_success_and_cooldown(cache, isolated, monkeypatch):
    enable(isolated)
    evidence = ai.build_rs_evidence("XLK", cache)
    post = Mock(return_value=provider_response(evidence))
    monkeypatch.setattr(ai.requests, "post", post)
    service = ai.AIReviewer()
    result = service.review(evidence)
    assert result["snapshot_id"] == evidence["snapshot_id"]
    assert result["observations"] == [evidence["observations"][0]]
    payload = post.call_args.kwargs["json"]
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert "tools" not in payload
    assert "unit-test-token" not in json.dumps(payload)
    assert post.call_args.kwargs["allow_redirects"] is False
    with pytest.raises(ai.ReviewUnavailable, match="minute"):
        service.review(evidence)
    assert post.call_count == 1


@pytest.mark.parametrize("failure", ["expired", "disabled", "model_changed", "mixed_refusal", "timeout"])
def test_publication_rechecks_contract_config_and_refusal(cache, isolated, monkeypatch, failure):
    enable(isolated)
    evidence = ai.build_rs_evidence("XLK", cache)

    def post(*args, **kwargs):
        if failure == "expired":
            ContractClock.current = NOW + timedelta(minutes=5)
        elif failure == "disabled":
            isolated[0]["SCANNER_AI_ENABLED"] = "0"
        elif failure == "model_changed":
            isolated[0]["SCANNER_AI_MODEL"] = "changed-model"
        elif failure == "mixed_refusal":
            return provider_response(evidence, [{"type": "output_text", "text": json.dumps(selection(evidence))},
                                                {"type": "refusal", "refusal": "no"}])
        else:
            raise requests.Timeout("unit-test-token")
        return provider_response(evidence)

    monkeypatch.setattr(ai.requests, "post", post)
    with pytest.raises(ai.ReviewUnavailable) as exc:
        ai.AIReviewer().review(evidence)
    assert "unit-test-token" not in str(exc.value)
    assert exc.value.__suppress_context__


def test_api_rebuild_rejects_changed_snapshot_after_mocked_model(cache, bars, isolated, monkeypatch):
    enable(isolated)
    evidence = ai.build_rs_evidence("XLK", cache)

    def post(*args, **kwargs):
        bars.iloc[-1, 0] += 1
        write_cache(cache / "XLK_1y.csv", bars)
        return provider_response(evidence)

    monkeypatch.setattr(ai.requests, "post", post)
    route = endpoint(cache, "/api/ai/review/{symbol}")
    with pytest.raises(HTTPException) as exc:
        route("XLK", web.AIReviewRequest(snapshot_id=evidence["snapshot_id"]), request())
    assert exc.value.status_code == 503
    assert "changed during" in exc.value.detail


def test_bridge_validates_contract_and_labels_offline_evidence(cache, isolated, monkeypatch):
    evidence = ai.build_rs_evidence("XLK", cache)
    status = {"enabled": False, "configured": False}
    get = Mock(side_effect=[status, evidence])
    monkeypatch.setattr(bridge, "_get_json", get)
    result = bridge.check_ai_readiness("XLK")
    assert result.service == "Disabled"
    assert result.evidence_date == "2026-09-10"
    assert not result.issue
    tampered = deepcopy(evidence)
    tampered["facts"]["bar_date"] = "2026-09-09"
    get.side_effect = [status, tampered]
    assert bridge.check_ai_readiness("XLK").evidence_date is None
    (cache / "SPY_1y.meta.json").unlink()
    get.side_effect = [status, ai.inspect_rs_evidence("XLK", cache)]
    result = bridge.check_ai_readiness("XLK")
    assert result.evidence_date == "2026-09-10"
    assert "Unverified" in result.issue
    assert "unverified" in result.sources
    assert isolated[1] == []


def test_bridge_page_initial_load_and_selection_never_fetch(cache, monkeypatch):
    get = Mock(side_effect=[{"enabled": False, "configured": False}, ai.build_rs_evidence("XLK", cache)])
    monkeypatch.setattr(bridge, "_get_json", get)
    app = AppTest.from_string("from qx.ui.ai_evidence import render_ai_evidence_link\nimport streamlit as st\nrender_ai_evidence_link(st)").run()
    get.assert_not_called()
    app.selectbox(key="command_ai_etf").set_value("XLK").run()
    get.assert_not_called()
    app.button(key="command_ai_check").click().run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["Disabled", "2026-09-10"]
    app.selectbox(key="command_ai_etf").set_value("XLE").run()
    assert not app.metric
    assert get.call_count == 2


def test_duplicate_close_columns_are_not_silently_selected(cache, bars):
    write_cache(cache / "XLK_1y.csv", pd.concat([bars, bars], axis=1))
    evidence = ai.inspect_rs_evidence("XLK", cache)
    assert evidence["validation"]["status"] == "unavailable"
    assert evidence["facts"]["return_1d"] is None


def test_same_missing_session_in_both_inputs_still_fails(cache, bars):
    bars = bars.drop(bars.index[-5])
    for ticker in ("XLK", "SPY"):
        write_cache(cache / f"{ticker}_1y.csv", bars)
    with pytest.raises(ai.ReviewUnavailable):
        ai.build_rs_evidence("XLK", cache)


def test_missing_credential_never_reaches_transport(cache, isolated):
    enable(isolated)
    isolated[0]["OPENAI_API_KEY"] = " "
    with pytest.raises(ai.ReviewUnavailable):
        ai.AIReviewer().review(ai.build_rs_evidence("XLK", cache))
    isolated[2].assert_not_called()


def test_api_rejects_stale_id_before_credentials(cache, isolated):
    enable(isolated)
    route = endpoint(cache, "/api/ai/review/{symbol}")
    with pytest.raises(HTTPException) as exc:
        route("XLK", web.AIReviewRequest(snapshot_id="a" * 64), request())
    assert exc.value.status_code == 409
    assert isolated[1] == []


def test_inspection_missing_cache_and_invalid_generation_never_refresh(cache, isolated):
    (cache / "XLK_1y.csv").unlink()
    get = endpoint(cache, "/api/ai/evidence/{symbol}")
    evidence = get("XLK")
    assert evidence["validation"]["status"] == "unavailable"
    assert evidence["facts"]["bar_date"] is None
    root = cache.parent / "dashboard_refresh"
    root.mkdir(exist_ok=True)
    (root / "current.json").write_text("[]")
    try:
        with pytest.raises(HTTPException) as exc:
            get("XLK")
        assert exc.value.status_code == 409
    finally:
        (root / "current.json").unlink()
    assert isolated[1] == []
    isolated[2].assert_not_called()


def test_selection_itself_rejects_expired_contract(cache):
    evidence = ai.build_rs_evidence("XLK", cache)
    ContractClock.current = NOW + timedelta(minutes=6)
    with pytest.raises(ai.ReviewUnavailable):
        ai.validate_selection(evidence, selection(evidence))


@pytest.mark.parametrize("output", [
    {"observations": ["invented"]}, {"observations": ["relative_strength", "relative_strength"]},
    {"observations": []}, {"checks": []}, {"checks": ["events", "events"]},
    {"checks": "events"}, {"snapshot_id": "a" * 64}, {"advice": "invented fact"},
])
def test_output_reference_rules_on_fresh_evidence(cache, output):
    evidence = ai.build_rs_evidence("XLK", cache)
    with pytest.raises(ai.ReviewUnavailable):
        ai.validate_selection(evidence, {**selection(evidence), **output})


def test_duplicate_json_fields_rejected_for_source_and_model(cache, isolated, monkeypatch):
    enable(isolated)
    evidence = ai.build_rs_evidence("XLK", cache)
    output = json.dumps(selection(evidence)).replace('"checks":', '"checks": ["risk"], "checks":')
    post = Mock(return_value=provider_response(evidence, [{"type": "output_text", "text": output}]))
    monkeypatch.setattr(ai.requests, "post", post)
    with pytest.raises(ai.ReviewUnavailable):
        ai.AIReviewer().review(evidence)
    metadata_path = cache / "XLK_1y.meta.json"
    metadata_path.write_text(metadata_path.read_text().replace('"actual_source":', '"actual_source": "yfinance", "actual_source":'))
    assert ai.inspect_rs_evidence("XLK", cache)["validation"]["status"] == "unverified"


def test_boolean_prices_are_not_numeric_evidence(cache, bars):
    bars["close"] = True
    write_cache(cache / "XLK_1y.csv", bars)
    assert ai.inspect_rs_evidence("XLK", cache)["validation"]["status"] == "unavailable"


def test_today_or_navigation_context_is_not_an_ai_contract(cache, isolated):
    enable(isolated)
    assert bridge.review_url("XLE") == "http://127.0.0.1:5173/?etf=XLE#ai-review"
    with pytest.raises(ValueError):
        web.AIReviewRequest(snapshot_id="a" * 64, as_of="2026-09-10", universe="SP500", created_at=NOW.isoformat())
    evidence = ai.build_rs_evidence("XLK", cache)
    route = endpoint(cache, "/api/ai/review/{symbol}")
    with pytest.raises(HTTPException) as exc:
        route("XLE", web.AIReviewRequest(snapshot_id=evidence["snapshot_id"]), request())
    assert exc.value.status_code == 409
    assert isolated[1] == []
