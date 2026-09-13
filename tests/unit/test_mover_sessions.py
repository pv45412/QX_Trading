from datetime import datetime, timedelta

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.market.sessions import completed_mover_bars


def history(end):
    dates = (
        mcal.get_calendar("NYSE")
        .schedule(start_date=pd.Timestamp(end) - timedelta(days=90), end_date=end)
        .index
    )
    return pd.DataFrame({"close": [100.0] * len(dates)}, index=dates)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("2026-09-08T14:00:00+00:00", "2026-09-04"),
        ("2026-09-12T14:00:00+00:00", "2026-09-11"),
        ("2026-11-27T18:29:00+00:00", "2026-11-25"),
        ("2026-11-27T18:30:00+00:00", "2026-11-27"),
        ("2026-03-09T20:29:00+00:00", "2026-03-06"),
        ("2026-03-09T20:30:00+00:00", "2026-03-09"),
    ],
)
def test_holidays_weekends_early_close_dst_and_buffer(when, expected):
    now = datetime.fromisoformat(when)
    result = completed_mover_bars(history(now.date()), now)
    assert result.index[-1].date().isoformat() == expected


def test_stale_or_missing_session_is_rejected():
    now = datetime.fromisoformat("2026-09-09T18:00:00+00:00")
    bars = history("2026-09-09")
    for bad in [bars.drop(pd.Timestamp("2026-09-08")), bars.drop(bars.index[-6])]:
        with pytest.raises(ValueError, match="Missing, stale"):
            completed_mover_bars(bad, now)


def test_naive_scan_time_and_future_bars_rejected():
    bars = history("2026-09-10")
    with pytest.raises(ValueError, match="timezone-aware"):
        completed_mover_bars(bars, datetime(2026, 9, 9))
    with pytest.raises(ValueError, match="Future-dated"):
        completed_mover_bars(bars, datetime.fromisoformat("2026-09-09T18:00:00+00:00"))
