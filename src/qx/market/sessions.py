"""NYSE completed-session policy for the US-equity movers lens."""

from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal  # type: ignore[import-untyped]


class IncompleteSessionWindow(ValueError):
    """Validated daily labels do not cover the required completed sessions."""

    def __init__(self, expected: date, last_available: date | None, required: int) -> None:
        self.expected = expected
        self.last_available = last_available
        self.required = required
        super().__init__(f"Missing, stale, or non-session daily bars; expected {required} sessions through {expected}")


@lru_cache(maxsize=32)
def _schedule(day: date) -> pd.DataFrame:
    return mcal.get_calendar("NYSE").schedule(start_date=day - timedelta(days=120), end_date=day)  # type: ignore[no-any-return]


def completed_mover_bars(
    bars: pd.DataFrame, as_of: datetime, *, required_sessions: int = 21,
) -> pd.DataFrame:
    if as_of.utcoffset() is None:
        raise ValueError("Scan time must be timezone-aware")
    if type(required_sessions) is not int or required_sessions < 1:
        raise ValueError("A positive completed-session count is required")
    today = as_of.astimezone(ZoneInfo("America/New_York")).date()
    schedule = _schedule(today)
    eligible = schedule.loc[schedule["market_close"] + pd.Timedelta(minutes=30) <= pd.Timestamp(as_of)]
    if len(eligible) < required_sessions:
        raise ValueError("Exchange calendar has insufficient session coverage")
    expected = pd.DatetimeIndex(eligible.index[-required_sessions:]).date
    # Provider daily indices are session labels, not intraday instants to convert.
    labels = pd.DatetimeIndex(bars.index).date
    if any(label > today for label in labels):
        raise ValueError("Future-dated daily bars")
    selected = bars.loc[pd.Series(labels <= expected[-1], index=bars.index)].copy()
    actual = pd.DatetimeIndex(selected.index).date
    if len(actual) < required_sessions or list(actual[-required_sessions:]) != list(expected):
        raise IncompleteSessionWindow(expected[-1], actual[-1] if len(actual) else None, required_sessions)
    return selected
