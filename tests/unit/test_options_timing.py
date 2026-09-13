import pandas as pd

from qx.options.timing import build_ema_timing_snapshot


def test_build_ema_timing_snapshot_scores_aligned_stack() -> None:
    snapshot = build_ema_timing_snapshot(
        daily=_bars(100, 1.0),
        hourly=_bars(100, 0.8),
        thirty_min=_bars(80, 0.6),
        fifteen_min=_bars(40, 0.4),
    )

    assert snapshot.score == 1.0
    assert snapshot.label == "Aligned"
    assert snapshot.trigger == "Trigger active"
    assert "H50 held" in snapshot.alignment


def test_build_ema_timing_snapshot_waits_for_lost_trigger() -> None:
    snapshot = build_ema_timing_snapshot(
        daily=_bars(100, 1.0),
        hourly=_bars(100, 0.8),
        thirty_min=_bars(80, 0.6),
        fifteen_min=_bars(40, -0.4),
    )

    assert snapshot.score < 1.0
    assert snapshot.trigger == "Wait for 15m 8 EMA reclaim"


def _bars(rows: int, step: float) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="h")
    close = pd.Series([100 + row * step for row in range(rows)], index=index)
    return pd.DataFrame({"Close": close}, index=index)
