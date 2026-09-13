from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.data.dashboard_refresh import DashboardRefresh, _completed_refresh_bars
from qx.data.stock_refresh import StockRefresh
from qx.market.ai_review import build_rs_evidence, validate_rs_evidence
from qx.market.sessions import completed_mover_bars


NOW = datetime(2026, 9, 11, 15, tzinfo=timezone.utc)


def daily_bars():
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date=NOW.date()).index
    bars = pd.DataFrame({"open":100., "high":101., "low":99., "close":100., "volume":1e6}, index=dates)
    bars.attrs["provenance"] = {
        "schema_version": 1, "actual_source": "schwab", "fallback_used": False,
        "retrieved_at": "2026-09-11T14:55:00+00:00", "last_bar_label": dates[-1].isoformat(),
    }
    return bars


def coordinator(tmp_path, provider, stock):
    if stock:
        (tmp_path / "sp100_symbols.csv").write_text("symbol\nXLE\n", encoding="utf-8")
        return StockRefresh(tmp_path / "bars", lambda: provider, "sp100")
    return DashboardRefresh(tmp_path / "bars", lambda: provider)


@pytest.mark.parametrize("stock", [False, True])
@pytest.mark.parametrize("timezone_name", [None, "America/New_York", "UTC"])
def test_publication_roundtrip_keeps_source_and_completed_window(tmp_path, stock, timezone_name):
    bars = daily_bars()
    if timezone_name:
        bars.index = bars.index.tz_localize(timezone_name)
        bars.attrs["provenance"]["last_bar_label"] = bars.index[-1].isoformat()
    original = bars.copy(deep=True)
    metadata = deepcopy(bars.attrs["provenance"])
    provider = SimpleNamespace(get_daily_bars=lambda request: bars.copy())
    refresh = coordinator(tmp_path, provider, stock)
    refresh.run(NOW)
    assert refresh.status()["status"] == "succeeded"
    evidence = build_rs_evidence("XLE", refresh.active_cache(), NOW)
    validate_rs_evidence(evidence, NOW, symbol="XLE")
    assert evidence["validation"]["live_eligible"] is True
    assert evidence["facts"]["bar_date"] == "2026-09-10"
    for source in evidence["facts"]["sources"].values():
        assert source["retrieved_at"] == metadata["retrieved_at"]
        assert source["actual_source"] == "schwab"
        assert source["last_bar_label"] == "2026-09-10T00:00:00"
        assert source["fallback_used"] is False
    assert bars.attrs["provenance"] == metadata
    pd.testing.assert_frame_equal(bars, original)
    assert not (tmp_path / "bars").exists()


@pytest.mark.parametrize("stock", [False, True])
@pytest.mark.parametrize("defect", ["time_of_day", "missing_22nd", "mismatched_source_label"])
def test_bad_window_retains_published_generation_and_releases_lock(tmp_path, stock, defect):
    bars = daily_bars()
    provider = SimpleNamespace(get_daily_bars=lambda request: bars.copy())
    refresh = coordinator(tmp_path, provider, stock)
    refresh.run(NOW)
    assert refresh.status()["status"] == "succeeded"
    pointer = (refresh.root / "current.json").read_bytes()
    published = refresh.active_cache()
    bad = bars.copy()
    if defect == "time_of_day":
        bad.index += pd.Timedelta(hours=1)
        bad.attrs["provenance"]["last_bar_label"] = bad.index[-1].isoformat()
    elif defect == "missing_22nd":
        # The old 21-session scanner policy accepts this; RS needs a 22nd close.
        completed = bars.loc[bars.index < pd.Timestamp(NOW.date())]
        bad = bad.drop(completed.index[-22])
        assert len(completed_mover_bars(bad, NOW)) >= 22
    else:
        bad.attrs["provenance"]["last_bar_label"] = "2026-09-10T00:00:00"
    provider.get_daily_bars = lambda request: bad.copy()
    refresh.run(NOW)
    assert refresh.status()["status"] == "failed"
    assert (refresh.root / "current.json").read_bytes() == pointer
    assert refresh.active_cache() == published
    assert refresh.reserve()
    refresh.run(NOW)


@pytest.mark.parametrize("provenance", [None, {}, {"actual_source": "unknown"}])
def test_filtering_does_not_invent_or_upgrade_provenance(provenance):
    bars = daily_bars()
    bars.attrs["provenance"] = deepcopy(provenance)
    result = _completed_refresh_bars(bars, NOW)
    assert result.attrs["provenance"] == provenance
    assert bars.attrs["provenance"] == provenance


@pytest.mark.parametrize("required", [0, -1, True, 1.5])
def test_session_window_requires_positive_integer(required):
    with pytest.raises(ValueError, match="positive completed-session count"):
        completed_mover_bars(daily_bars(), NOW, required_sessions=required)
