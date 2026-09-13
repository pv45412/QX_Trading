import pandas as pd
import pytest

from qx.patterns.rectangle_v2 import (
    RectangleV2Config,
    confirmed_pivots,
    detect_rectangle_candidates,
)


def test_detects_confirmed_parallel_rectangle_candidates() -> None:
    bars = _rectangle_bars()

    candidates = detect_rectangle_candidates(
        bars,
        RectangleV2Config(window_sizes=(20,), pivot_order=2, min_containment_ratio=0.90),
    )

    assert candidates
    latest = candidates[-1]
    assert latest.status == "confirmed_rectangle_candidate"
    assert len(latest.support_pivots) >= 2
    assert len(latest.resistance_pivots) >= 2
    assert latest.parallelism_pct == 0.0
    assert latest.containment_ratio >= 0.90


def test_pivot_is_not_available_until_right_side_is_complete() -> None:
    bars = _rectangle_bars().iloc[:10]

    pivots = confirmed_pivots(bars, pivot_order=2)

    assert all(pivot.confirmed_index <= len(bars) - 1 for pivot in pivots)
    assert all(pivot.index <= len(bars) - 3 for pivot in pivots)


def test_future_bars_do_not_change_historical_candidate() -> None:
    history = _rectangle_bars()
    extended = pd.concat([history, _future_bars()])
    config = RectangleV2Config(window_sizes=(20,), pivot_order=2, min_containment_ratio=0.90)

    original = detect_rectangle_candidates(history, config)
    extended_candidates = detect_rectangle_candidates(extended, config)
    historical = tuple(candidate for candidate in extended_candidates if candidate.end_index < len(history))

    assert historical == original


def test_rejects_nonparallel_pivot_lines() -> None:
    bars = _rectangle_bars(support_step=0.0, resistance_step=0.30)

    candidates = detect_rectangle_candidates(
        bars,
        RectangleV2Config(window_sizes=(20,), pivot_order=2, max_parallelism_pct=0.08),
    )

    assert candidates == ()


def test_deduplicates_near_identical_bounded_windows() -> None:
    bars = _rectangle_bars()

    candidates = detect_rectangle_candidates(
        bars,
        RectangleV2Config(window_sizes=(20, 21), pivot_order=2, min_containment_ratio=0.90),
    )

    latest_end = len(bars) - 1
    assert len([candidate for candidate in candidates if candidate.end_index == latest_end]) == 1


@pytest.mark.parametrize(
    "column,value",
    [("high", float("nan")), ("low", 0.0), ("close", float("inf"))],
)
def test_rejects_invalid_prices(column: str, value: float) -> None:
    bars = _rectangle_bars()
    bars.loc[bars.index[0], column] = value

    with pytest.raises(ValueError, match="price"):
        detect_rectangle_candidates(bars)


def test_rejects_inverted_high_low() -> None:
    bars = _rectangle_bars()
    bars.loc[bars.index[0], "high"] = 99.0

    with pytest.raises(ValueError, match="inverted"):
        detect_rectangle_candidates(bars)


def _rectangle_bars(support_step: float = 0.0, resistance_step: float = 0.0) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for index in range(20):
        support = 100.0 + support_step * index
        resistance = 110.0 + resistance_step * index
        phase = index % 4
        if phase == 0:
            low, high, close = support, 106.0, 105.0
        elif phase == 2:
            low, high, close = 104.0, resistance, 105.0
        else:
            low, high, close = 103.0, 107.0, 105.0
        rows.append({"high": high, "low": low, "close": close})
    return pd.DataFrame(rows, index=pd.date_range("2026-01-01", periods=20, freq="B"))


def _future_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"high": 140.0, "low": 130.0, "close": 135.0},
            {"high": 145.0, "low": 132.0, "close": 140.0},
            {"high": 150.0, "low": 135.0, "close": 145.0},
        ],
        index=pd.date_range("2026-01-29", periods=3, freq="B"),
    )
