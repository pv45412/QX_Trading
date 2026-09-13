from qx.patterns.weekly import analyze_weekly_context, daily_to_weekly
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_daily_to_weekly_builds_ohlcv_bars() -> None:
    weekly = daily_to_weekly(_clean_rectangle_bars())

    assert not weekly.empty
    assert list(weekly.columns) == ["open", "high", "low", "close", "volume"]
    assert weekly["high"].max() >= weekly["low"].min()


def test_weekly_context_scores_constructive_or_extended_state() -> None:
    context = analyze_weekly_context(_clean_rectangle_bars())

    assert 0 <= context.score <= 1
    assert context.status
    assert context.sma10 > 0
    assert context.sma30 > 0
