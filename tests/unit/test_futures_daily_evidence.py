from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest

from qx.market.futures_daily_evidence import daily_context_evidence, daily_series_evidence
from qx.market.spx_dashboard import build_spx_dashboard
from tests.unit.test_spx_dashboard import StaticProvider, _bars


NOW = datetime(2026, 9, 11, 18, tzinfo=timezone.utc)


def sourced_bars():
    bars = _bars(100.0, 0.1)
    bars.attrs["provenance"] = {
        "schema_version": 1, "actual_source": "yfinance", "fallback_used": True,
        "retrieved_at": NOW.isoformat(), "last_bar_label": bars.index[-1].isoformat(),
    }
    return bars


def evidence(bars):
    return daily_series_evidence("ES=F", bars, checked_at=NOW)


def test_source_and_labels_are_bound_to_series_without_certifying_freshness():
    bars = sourced_bars()
    row = evidence(bars)
    assert row["status"] == "daily_reference"
    assert row["actual_source"] == "yfinance" and row["fallback_used"] is True
    assert row["latest_bar_label"] == bars.index[-1].isoformat()
    assert row["prior_bar_label"] == bars.index[-2].isoformat()
    assert row["freshness"] == row["session_completion"] == "unverified"
    assert row["contract_continuity"] == "unverified"
    assert not row["cash_close_synchronized"] and not row["live_signal_eligible"]
    changed = bars.copy()
    changed.iloc[-1, changed.columns.get_loc("volume")] += 1
    assert evidence(changed)["bars_sha256"] != row["bars_sha256"]
    report = daily_context_evidence([row], checked_at=NOW)
    assert json.loads(json.dumps(report, allow_nan=False)) == report


@pytest.mark.parametrize("metadata", [None, {}, {"schema_version": 1}, "invalid"])
def test_missing_or_malformed_provenance_is_unknown(metadata):
    bars = sourced_bars()
    bars.attrs["provenance"] = metadata
    row = evidence(bars)
    assert row["status"] == "daily_reference"
    assert row["actual_source"] == "unknown"
    assert row["retrieved_at"] is None and row["fallback_used"] is None


@pytest.mark.parametrize("field,value", [
    ("last_bar_label", "2020-01-01T00:00:00"),
    ("retrieved_at", (NOW + timedelta(days=1)).isoformat()),
])
def test_mismatched_metadata_does_not_attribute_series(field, value):
    bars = sourced_bars()
    bars.attrs["provenance"][field] = value
    row = evidence(bars)
    assert row["provenance_status"] == "metadata_mismatch"
    assert row["actual_source"] == "unknown"


@pytest.mark.parametrize("defect,status", [
    ("duplicate", "invalid_dates"), ("unsorted", "invalid_dates"),
    ("undated", "invalid_dates"), ("nat", "invalid_dates"),
    ("future", "future_dated"), ("nan", "invalid_ohlcv"),
    ("inf", "invalid_ohlcv"), ("geometry", "invalid_ohlcv"),
    ("negative_volume", "invalid_ohlcv"), ("missing_column", "invalid_ohlcv"),
    ("boolean", "invalid_ohlcv"), ("short", "insufficient_history"),
])
def test_invalid_history_is_withheld_in_every_es_view(defect, status):
    bars = sourced_bars()
    if defect == "duplicate":
        bars = pd.concat([bars, bars.tail(1)])
    elif defect == "unsorted":
        bars = bars.iloc[::-1]
    elif defect == "undated":
        bars = bars.reset_index(drop=True)
    elif defect == "nat":
        bars.index = pd.DatetimeIndex([*bars.index[:-1], pd.NaT])
    elif defect == "future":
        bars.index = pd.bdate_range("2099-01-01", periods=len(bars))
    elif defect == "nan":
        bars.iloc[-1, 3] = float("nan")
    elif defect == "inf":
        bars.iloc[-1, 3] = float("inf")
    elif defect == "geometry":
        bars.iloc[-1, 1] = 1
    elif defect == "negative_volume":
        bars.iloc[-1, 4] = -1
    elif defect == "missing_column":
        bars = bars.drop(columns="close")
    elif defect == "boolean":
        bars["volume"] = True
    elif defect == "short":
        bars = bars.tail(19)
    assert evidence(bars)["status"] == status
    assert evidence(bars)["chart_bars"] == []
    dashboard = build_spx_dashboard(StaticProvider({"SPY": _bars(100, .1), "ES=F": bars}))
    assert dashboard.es_close is None and dashboard.es_overnight_move is None
    assert dashboard.es_levels.close is None
    assert next(row for row in dashboard.futures_rows if row.symbol == "ES=F").close is None
    assert next(row for row in dashboard.timing_rows if row.symbol == "ES=F").trigger_level is None
    assert dashboard.opening_gap.es_change_pct is None


def test_alignment_requires_both_daily_return_endpoints():
    es, nq = sourced_bars(), sourced_bars()
    # Same final bar but different prior bar must not support relative performance.
    nq = nq.drop(nq.index[-2])
    dashboard = build_spx_dashboard(StaticProvider({"SPY": es, "ES=F": es, "NQ=F": nq}))
    assert not dashboard.daily_evidence["daily_labels_aligned"]
    assert any("relative daily performance withheld" in note for note in dashboard.confirmation_notes)
    assert not any("percentage points" in note for note in dashboard.confirmation_notes)
    assert dashboard.es_close is not None and dashboard.nq_close is not None


def test_missing_one_series_keeps_other_series_and_records_unavailable():
    bars = sourced_bars()
    dashboard = build_spx_dashboard(StaticProvider({"SPY": bars, "NQ=F": bars}))
    es, nq = dashboard.daily_evidence["rows"]
    assert es["status"] == "unavailable" and nq["status"] == "daily_reference"
    assert dashboard.es_close is None and dashboard.nq_close is not None
    assert nq["daily_facts"]["close"] == dashboard.nq_close
    assert nq["daily_facts"]["return_1d"] == dashboard.nq_overnight_move
    assert nq["daily_facts"]["prior_high"] == dashboard.nq_levels.prior_high
    assert es["daily_facts"] is None
    assert dashboard.daily_evidence["schema_version"] == "qx.futures-daily-context.v1"
    assert not dashboard.daily_evidence["live_signal_eligible"]


def test_cutoff_cannot_be_bypassed_and_naive_clocks_are_rejected():
    bars = sourced_bars()
    with pytest.raises(ValueError, match="aware clock"):
        daily_series_evidence("ES=F", bars, checked_at=NOW.replace(tzinfo=None))
    result = daily_series_evidence(
        "ES=F", bars, checked_at=NOW, as_of=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert result["status"] == "future_dated"


def test_daily_chart_uses_exact_observed_prices_volume_and_reference_levels():
    from qx.ui.futures_workspace import daily_chart

    bars = sourced_bars()
    dashboard = build_spx_dashboard(StaticProvider({"SPY": bars, "ES=F": bars}))
    row = dashboard.daily_evidence["rows"][0]
    history = row["chart_bars"]
    assert len(history) == 60
    assert [item["close"] for item in history] == bars["close"].tail(60).tolist()
    assert [item["bar_label"] for item in history] == [date.isoformat() for date in bars.index[-60:]]
    chart = daily_chart(history[-20:], dashboard.es_levels, "ES=F")
    assert list(chart.data[0].close) == bars["close"].tail(20).tolist()
    assert list(chart.data[0].high) == bars["high"].tail(20).tolist()
    assert list(chart.data[1].y) == bars["volume"].tail(20).tolist()
    assert [shape.y0 for shape in chart.layout.shapes] == [
        dashboard.es_levels.prior_high, dashboard.es_levels.prior_low,
    ]
