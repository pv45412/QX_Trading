import pandas as pd
import pytest

from qx.patterns.rectangle_v2 import RectangleV2Config
from qx.patterns.rectangle_v2_audit import audit_rectangle_candidates


def test_audit_is_prefix_invariant_and_records_candidate_end_dates() -> None:
    history = _rectangle_bars()
    extended = pd.concat([history, _future_bars()])
    config = RectangleV2Config(window_sizes=(20,), pivot_order=2, min_containment_ratio=0.90)

    original = audit_rectangle_candidates(history, config)
    extended_audit = audit_rectangle_candidates(extended, config)
    historical = tuple(
        observation
        for observation in extended_audit.observations
        if observation.cutoff_date <= history.index[-1]
    )

    assert original.observations
    assert historical == original.observations
    assert all(
        observation.candidate_end_date <= observation.cutoff_date
        for observation in original.observations
    )
    assert original.summary.candidate_observation_count == len(original.observations)
    assert original.summary.completed_cutoff_count == 1


def test_audit_rejects_non_chronological_indexes() -> None:
    descending = _rectangle_bars().iloc[::-1]
    duplicate = _rectangle_bars().rename(
        index={pd.Timestamp("2026-01-02"): pd.Timestamp("2026-01-01")}
    )
    non_datetime = _rectangle_bars().set_axis(range(20))

    for bars in (descending, duplicate, non_datetime):
        with pytest.raises(ValueError, match="chronological audit"):
            audit_rectangle_candidates(bars)


def _rectangle_bars() -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for index in range(20):
        phase = index % 4
        if phase == 0:
            low, high, close = 100.0, 106.0, 105.0
        elif phase == 2:
            low, high, close = 104.0, 110.0, 105.0
        else:
            low, high, close = 103.0, 107.0, 105.0
        rows.append({"high": high, "low": low, "close": close})
    return pd.DataFrame(rows, index=pd.date_range("2026-01-01", periods=20, freq="B"))


def _future_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"high": 140.0, "low": 130.0, "close": 135.0},
            {"high": 145.0, "low": 132.0, "close": 140.0},
        ],
        index=pd.date_range("2026-01-29", periods=2, freq="B"),
    )
