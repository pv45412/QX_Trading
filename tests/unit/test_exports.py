from datetime import date

from qx.exports.scanner_results import SCANNER_RESULTS_COLUMNS, scanner_results_frame
from qx.patterns.rectangle import analyze_rectangle
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_scanner_results_frame_matches_quantx_schema() -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())

    frame = scanner_results_frame([candidate], scan_date=date(2026, 5, 31))

    assert list(frame.columns) == SCANNER_RESULTS_COLUMNS
    row = frame.iloc[0].to_dict()
    assert row["date"] == "2026-05-31"
    assert row["ticker"] == "TEST"
    assert row["timeframe"] == "1D"
    assert row["pattern"] == "rectangle"
    assert row["score"] == 100.0
    assert candidate.weekly_context is not None
    assert row["weekly_status"] == candidate.weekly_context.status
    assert row["entry"] == round(candidate.metrics.breakout_level, 2)
    assert row["stop"] == round(candidate.metrics.failure_level, 2)
    assert row["target"] > row["entry"]
