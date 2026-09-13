from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from qx.backtesting import evaluation_protocol as protocol
from qx.backtesting.evaluation_report import (
    evaluate_fixed_snapshot,
    replay_evaluation_report,
    report_json,
    restore_snapshot,
    snapshot_payload,
)
from qx.backtesting.strategy_lab import STRATEGY_GRID, evaluate_strategy_snapshot
from qx.models.scan import RectangleScanParameters
from tests.unit.test_strategy_evaluation_protocol_20260911 import (
    EvaluationProvider,
    evaluation_bars,
    fixed_spec,
    predictable_setups,  # noqa: F401
)


pytestmark = pytest.mark.usefixtures("predictable_setups")
OBSERVED = datetime(2026, 9, 11, 14, tzinfo=timezone.utc)


def future_bars():
    bars = evaluation_bars()
    bars.index = pd.date_range("2099-01-01", periods=len(bars), freq="B")
    return bars


@pytest.mark.parametrize("historical_prefix", [False, True])
def test_future_symbol_cannot_expand_valid_training_or_change_selection(historical_prefix):
    good, future = evaluation_bars(), future_bars()
    baseline_frames = {"GOOD": good}
    if historical_prefix:
        baseline_frames["BAD"] = good.copy()
    bad = pd.concat([good, future]) if historical_prefix else future
    extended_frames = {**baseline_frames, "BAD": bad}
    reports = []
    for frames in (baseline_frames, extended_frames):
        symbols = sorted(frames)
        snapshot = protocol.capture_evaluation_snapshot(
            symbols, EvaluationProvider(frames), "2y", observed_at=OBSERVED)
        spec = {**fixed_spec(symbols), "kind": "training_selection", "grid": STRATEGY_GRID}
        reports.append(evaluate_strategy_snapshot(spec, snapshot).report)
    baseline, extended = reports
    assert baseline["split"]["holdout_start"] == str(good.index[360])
    assert extended["split"] == baseline["split"]
    assert extended["selected_parameters"] == baseline["selected_parameters"]
    assert extended["selected_parameters"]["entry_window_bars"] == 3
    for phase in ("training", "holdout"):
        before, after = [report["results"][phase] for report in reports]
        assert next(row for row in before["result"]["results"] if row["symbol"] == "GOOD") == next(
            row for row in after["result"]["results"] if row["symbol"] == "GOOD")
        good_coverage = [next(row for row in payload["coverage"] if row["symbol"] == "GOOD")
                         for payload in (before, after)]
        assert good_coverage[0] == good_coverage[1]
        if phase == "training":
            assert good_coverage[1]["history_bars"] == 360
            assert good_coverage[1]["trades"] == 69
    bad_coverage = next(row for row in extended["results"]["holdout"]["coverage"]
                        if row["symbol"] == "BAD")
    assert bad_coverage["status"] == "future_dated_history"
    assert len(bad_coverage["future_dates"]) == len(future)
    record = next(row for row in extended["data"]["symbols"] if row["symbol"] == "BAD")
    assert record["bar_count"] == len(bad)
    restored = restore_snapshot(json.loads(report_json(extended))["data"])
    pd.testing.assert_frame_equal(restored.bars_by_symbol["BAD"], bad, check_freq=False)
    replayed = replay_evaluation_report(extended)
    assert replayed["report_id"] == extended["report_id"]
    assert replayed["data"] == extended["data"]
    assert replayed["results"] == extended["results"]


def test_all_future_history_has_no_split_selection_or_evaluated_phases(monkeypatch):
    bars = future_bars()
    snapshot = protocol.capture_evaluation_snapshot(
        ["FUTURE"], EvaluationProvider({"FUTURE": bars}), "2y", observed_at=OBSERVED)
    assert protocol.holdout_start(snapshot, protocol.EvaluationProtocol()) is None

    def forbidden(*args, **kwargs):
        raise AssertionError("Future-only history must never reach the backtest engine")

    monkeypatch.setattr(protocol, "backtest_rectangle_breakouts", forbidden)
    for phase in ("training", "holdout"):
        result = protocol.evaluate_phase(
            snapshot, RectangleScanParameters(), protocol.evaluation_parameters(),
            phase=phase, split=None)
        assert result.result.total_trades == 0
        assert result.result.results == []
        assert result.coverage[0]["status"] == "future_dated_history"
        assert result.coverage[0]["history_bars"] == len(bars)
        assert result.coverage[0]["future_dates"] == list(bars.index.strftime("%Y-%m-%d"))
        assert any("Future-dated" in warning for warning in result.warnings)
    spec = {**fixed_spec(["FUTURE"]), "kind": "training_selection", "grid": STRATEGY_GRID}
    report = evaluate_strategy_snapshot(spec, snapshot).report
    assert report["selected_parameters"] is None
    assert report["results"]["holdout"] is None
    assert all(row["trades"] == 0 for row in report["results"]["training_grid"])
    assert report["data"]["symbols"][0]["bar_count"] == len(bars)
    assert replay_evaluation_report(report)["report_id"] == report["report_id"]
    fixed = evaluate_fixed_snapshot(fixed_spec(["FUTURE"]), snapshot)
    assert fixed["results"]["holdout"]["coverage"][0]["status"] == "future_dated_history"
    assert replay_evaluation_report(fixed)["report_id"] == fixed["report_id"]


def test_split_uses_recorded_et_capture_day_after_json_restore():
    bars = evaluation_bars(10)
    bars.index = pd.date_range("2026-09-01", periods=10, freq="D")
    observed = datetime(2026, 9, 10, 1, tzinfo=timezone.utc)
    snapshot = protocol.capture_evaluation_snapshot(
        ["TEST"], EvaluationProvider({"TEST": bars}), "2y", observed_at=observed)
    restored = restore_snapshot(json.loads(json.dumps(snapshot_payload(snapshot))))
    assert restored.date_checks["TEST"]["observed_date_et"] == "2026-09-09"
    assert restored.date_checks["TEST"]["future_dates"] == ["2026-09-10"]
    assert protocol.holdout_start(restored, protocol.EvaluationProtocol()) == bars.index[6]
    pd.testing.assert_frame_equal(restored.bars_by_symbol["TEST"], bars, check_freq=False)
    # Non-session labels remain visible and in the dated history; they are not silently repaired.
    assert "2026-09-07" in restored.date_checks["TEST"]["non_session_dates"]


@pytest.mark.parametrize("observed_date", [None, "", "invalid", "20260911"])
def test_missing_or_invalid_capture_date_cannot_admit_future_labels(observed_date):
    snapshot = protocol.capture_evaluation_snapshot(
        ["TEST"], EvaluationProvider({"TEST": future_bars()}), "2y", observed_at=OBSERVED)
    if observed_date is None:
        snapshot.date_checks.clear()
    else:
        snapshot.date_checks["TEST"]["observed_date_et"] = observed_date
    assert protocol.holdout_start(snapshot, protocol.EvaluationProtocol()) is None
