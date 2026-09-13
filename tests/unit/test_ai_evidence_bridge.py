from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pandas_market_calendars as mcal
import pytest
import requests
from streamlit.testing.v1 import AppTest

from qx.ui import ai_evidence
from qx.data.cache import _write_cached_bars
from qx.market import ai_review


NOW = datetime(2026, 9, 10, 14, tzinfo=timezone.utc)


class BridgeClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


@pytest.fixture
def evidence(tmp_path):
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-05-01", end_date="2026-09-09").index
    bars = pd.DataFrame({key: [100.0 + n / 10 for n in range(len(dates))]
                         for key in ("open", "high", "low", "close", "volume")}, index=dates)

    def build(symbol="XLK"):
        for ticker in (symbol, "SPY"):
            bars.attrs["provenance"] = {"schema_version": 1, "actual_source": "yfinance" if ticker == "SPY" else "schwab",
                                       "fallback_used": ticker == "SPY", "retrieved_at": (NOW - timedelta(minutes=1)).isoformat(),
                                       "last_bar_label": dates[-1].isoformat()}
            _write_cached_bars(tmp_path / f"{ticker}_1y.csv", bars, object())
        return ai_review.build_rs_evidence(symbol, tmp_path, NOW)

    return build


def response(body, code=200):
    return SimpleNamespace(status_code=code, json=lambda: body)


@pytest.fixture(autouse=True)
def forbid_model_requests(monkeypatch):
    monkeypatch.setattr(ai_review, "datetime", BridgeClock)
    monkeypatch.setattr(ai_evidence, "datetime", BridgeClock)
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("No real network requests allowed")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("No model requests allowed")))


def mock_get(monkeypatch, *responses):
    get = Mock(side_effect=responses)
    monkeypatch.setattr(ai_evidence.requests, "get", get)
    return get


@pytest.mark.parametrize("enabled,configured,label", [
    (False, False, "Disabled"), (False, True, "Disabled"),
    (True, False, "Not configured"), (True, True, "Configured; untested"),
])
def test_readiness_never_tests_live_model_and_keeps_data_separate(monkeypatch, evidence, enabled, configured, label):
    get = mock_get(monkeypatch, response(dict(enabled=enabled, configured=configured)), response(evidence()))
    result = ai_evidence.check_ai_readiness("XLK")
    assert result.service == label
    assert result.evidence_date == "2026-09-09"
    assert result.sources == "XLK: schwab | SPY: yfinance (fallback)"
    assert result.issue == ""
    assert [call.args[0] for call in get.call_args_list] == [
        "http://127.0.0.1:8510/api/ai/status", "http://127.0.0.1:8510/api/ai/evidence/XLK"]
    assert all(call.kwargs == dict(timeout=(1, 4), allow_redirects=False) for call in get.call_args_list)


@pytest.mark.parametrize("failure", [requests.Timeout("private detail"), response({}, 503),
                                     response({"enabled": "false", "configured": False}), response([])])
def test_api_failure_is_unknown_not_disabled_and_stops_evidence_request(monkeypatch, failure):
    get = mock_get(monkeypatch, failure)
    result = ai_evidence.check_ai_readiness("XLK")
    assert result.service == "Unavailable"
    assert result.evidence_date is None
    assert "private" not in result.issue
    assert get.call_count == 1


@pytest.mark.parametrize("failure", [requests.ConnectionError("private detail"), response({}, 409),
                                     response({}, 302), response([]), response({})])
def test_evidence_failure_retains_verified_disabled_status(monkeypatch, failure):
    mock_get(monkeypatch, response(dict(enabled=False, configured=False)), failure)
    result = ai_evidence.check_ai_readiness("XLK")
    assert result.service == "Disabled"
    assert result.evidence_date is None
    assert result.issue
    assert "private" not in result.issue


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(expires_at="2020-01-01T00:00:00+00:00"),
    lambda data: data.update(checked_at="2099-01-01T00:00:00+00:00"),
    lambda data: data.update(checked_at="2026-09-09T00:00:00"),
    lambda data: data.update(schema_version="unknown"),
    lambda data: data.update(snapshot_id="unknown"),
    lambda data: data["facts"].update(symbol="XLE"),
    lambda data: data["facts"].update(benchmark="ES"),
    lambda data: data["facts"]["sources"]["XLK"].update(actual_source="unknown"),
    lambda data: data["facts"]["sources"]["XLK"].update(fallback_used="false"),
])
def test_mismatched_or_expired_evidence_is_not_presented_as_ready(monkeypatch, evidence, mutation):
    body = evidence()
    mutation(body)
    mock_get(monkeypatch, response(dict(enabled=False, configured=False)), response(body))
    assert ai_evidence.check_ai_readiness("XLK").evidence_date is None


def test_invalid_symbol_never_becomes_url_or_request(monkeypatch):
    get = mock_get(monkeypatch)
    with pytest.raises(ValueError, match="Unsupported ETF"):
        ai_evidence.check_ai_readiness("../secret")
    assert get.call_count == 0
    assert ai_evidence.review_url("XLE") == "http://127.0.0.1:5173/?etf=XLE#ai-review"


def test_today_bridge_is_on_demand_and_drops_old_results_on_selection(monkeypatch, evidence):
    get = mock_get(monkeypatch, response(dict(enabled=False, configured=False)), response(evidence()))
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.ai_evidence import render_ai_evidence_link
render_ai_evidence_link(st)
''').run()
    assert not app.exception
    assert get.call_count == 0
    app.selectbox(key="command_ai_etf").set_value("XLK").run()
    app.button(key="command_ai_check").click().run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["Disabled", "2026-09-09"]
    assert any("not been AI-reviewed" in caption.value for caption in app.caption)
    assert get.call_count == 2
    app.selectbox(key="command_ai_etf").set_value("XLE").run()
    assert not app.metric
    assert get.call_count == 2
    assert "?etf=XLE#ai-review" in app.get("link_button")[0].proto.url


def test_today_bridge_api_offline_is_a_warning_not_a_page_exception(monkeypatch):
    mock_get(monkeypatch, requests.Timeout("private detail"))
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.ai_evidence import render_ai_evidence_link
render_ai_evidence_link(st)
''').run()
    app.button(key="command_ai_check").click().run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["Unavailable", "Unavailable"]
    assert "readiness is unknown" in app.warning[0].value


@pytest.mark.parametrize("context", [None, {}, {"as_of": "2026-02-30", "snapshot": "0", "secret": "not-for-links"}])
def test_no_valid_context_preserves_legacy_review_url(context):
    assert ai_evidence.review_url("XLE", context) == "http://127.0.0.1:5173/?etf=XLE#ai-review"


def test_review_url_preserves_only_valid_navigation_context():
    context = {"universe": "sp500", "sector": "Information Technology", "symbol": "NVDA", "etf": "xlk",
               "period": "2y", "as_of": "2026-09-08", "snapshot": "92", "created_at": NOW.isoformat(),
               "secret": "not-for-links"}
    original = dict(context)
    url = urlparse(ai_evidence.review_url("XLE", context))
    assert url.fragment == "ai-review"
    assert parse_qs(url.query) == {"universe": ["sp500"], "sector": ["Information Technology"],
                                    "symbol": ["XLE"], "etf": ["XLE"], "period": ["2y"],
                                    "as_of": ["2026-09-08"], "snapshot": ["92"]}
    assert context == original


@pytest.mark.parametrize("requested_date,warning", [("2026-09-09", False), ("2026-09-08", True)])
def test_today_context_defaults_etf_without_relabeling_evidence(monkeypatch, evidence, requested_date, warning):
    get = mock_get(monkeypatch, response(dict(enabled=False, configured=False)), response(evidence("XLE")))
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.ai_evidence import render_ai_evidence_link
render_ai_evidence_link(st)
''')
    app.query_params.update(etf="xle", symbol="NVDA", as_of=requested_date, snapshot="92", universe="sp500", secret="not-for-links")
    app.run()
    assert not app.exception
    assert app.selectbox(key="command_ai_etf").value == "XLE"
    get.assert_not_called()
    initial = parse_qs(urlparse(app.get("link_button")[0].proto.url).query)
    assert initial == {"etf": ["XLE"], "symbol": ["XLE"], "as_of": [requested_date], "snapshot": ["92"], "universe": ["sp500"]}
    app.button(key="command_ai_check").click().run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["Disabled", "2026-09-09"]
    assert any("does not validate" in item.value for item in app.warning) is warning
    assert parse_qs(urlparse(app.get("link_button")[0].proto.url).query) == initial
    assert [call.args[0] for call in get.call_args_list] == [
        "http://127.0.0.1:8510/api/ai/status", "http://127.0.0.1:8510/api/ai/evidence/XLE"]
    app.selectbox(key="command_ai_etf").set_value("XLK").run()
    assert not app.metric
    assert get.call_count == 2
    changed = parse_qs(urlparse(app.get("link_button")[0].proto.url).query)
    assert changed == {**initial, "etf": ["XLK"], "symbol": ["XLK"]}


@pytest.mark.parametrize("etf", ["AAPL", "<script>"])
def test_unsupported_context_etf_cannot_become_selection_or_request(monkeypatch, etf):
    get = mock_get(monkeypatch)
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.ai_evidence import render_ai_evidence_link
render_ai_evidence_link(st)
''')
    app.query_params.update(etf=etf, as_of="2026-09-08", snapshot="92")
    app.run()
    assert not app.exception
    selected = app.selectbox(key="command_ai_etf").value
    assert selected == next(iter(ai_evidence.DASHBOARD_ETFS.values()))
    query = parse_qs(urlparse(app.get("link_button")[0].proto.url).query)
    assert query == {"etf": [selected], "symbol": [selected], "as_of": ["2026-09-08"], "snapshot": ["92"]}
    get.assert_not_called()
