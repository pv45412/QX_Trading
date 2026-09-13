from types import SimpleNamespace

import pandas as pd
import pytest

from qx.backtesting import engine, evaluation_protocol as protocol
from qx.backtesting.evaluation_report import (
    evaluate_fixed_snapshot,
    evaluation_spec,
    replay_evaluation_report,
)
from qx.backtesting.strategy_lab import compare_rectangle_strategies
from qx.models.scan import RectangleScanParameters


def evaluation_bars(count=480):
    return pd.DataFrame({
        "open": [100.0] * count, "high": [104.0] * count, "low": [99.0] * count,
        "close": [103.0] * count, "volume": [1_000_000.0] * count,
    }, index=pd.date_range("2020-01-01", periods=count, freq="B"))


class EvaluationProvider:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def get_daily_bars(self, request):
        self.calls.append(request.symbol)
        if request.symbol not in self.frames:
            raise ValueError("private provider response")
        return self.frames[request.symbol]


@pytest.fixture
def predictable_setups(monkeypatch):
    def setup(symbol, history, parameters):
        return SimpleNamespace(setup_score=1.0, metrics=SimpleNamespace(
            breakout_level=float(history.iloc[-1]["open"])))
    monkeypatch.setattr(engine, "analyze_rectangle", setup)


def fixed_spec(symbols):
    return evaluation_spec(symbols, universe="Custom", period="2y", profile="Test",
                           scan_parameters=RectangleScanParameters(),
                           parameters=protocol.evaluation_parameters(),
                           protocol=protocol.EvaluationProtocol())


def test_shared_cost_defaults_reach_every_training_and_holdout_call(monkeypatch, predictable_setups):
    calls = []
    original = protocol.backtest_rectangle_breakouts

    def record(symbol, bars, scan, parameters):
        calls.append((len(bars), parameters.model_copy()))
        return original(symbol, bars, scan, parameters)

    monkeypatch.setattr(protocol, "backtest_rectangle_breakouts", record)
    provider = EvaluationProvider({"TEST": evaluation_bars()})
    result = compare_rectangle_strategies([" test ", "TEST"], provider, period="2y",
                                          scan_parameters=RectangleScanParameters())
    assert provider.calls == ["TEST"]
    assert len(calls) == 13
    assert [length for length, _ in calls] == [360] * 12 + [480]
    assert {(p.fee_bps_per_side, p.slippage_bps_per_side) for _, p in calls} == {(0.0, 5.0)}
    snapshot = protocol.capture_evaluation_snapshot(["TEST"], provider, "2y")
    fixed = evaluate_fixed_snapshot(fixed_spec(["TEST"]), snapshot)
    assert fixed["spec"]["costs"] == result.report["spec"]["costs"]
    assert fixed["split"]["holdout_start"] == result.report["split"]["holdout_start"]
    assert all(trade["return_pct"] < trade["gross_return_pct"]
               for item in fixed["results"]["holdout"]["result"]["results"] for trade in item["trades"])


@pytest.mark.parametrize("holdout_low", [50.0, 0.0, float("nan"), "invalid"])
def test_heldout_prices_cannot_change_training_rank_or_selection(predictable_setups, holdout_low):
    original = evaluation_bars()
    changed = original.astype(object)
    changed.iloc[360:, changed.columns.get_loc("low")] = holdout_low
    first = compare_rectangle_strategies(["TEST"], EvaluationProvider({"TEST": original}),
                                         period="2y", scan_parameters=RectangleScanParameters())
    second = compare_rectangle_strategies(["TEST"], EvaluationProvider({"TEST": changed}),
                                          period="2y", scan_parameters=RectangleScanParameters())
    assert first.rows == second.rows
    assert first.report["selected_parameters"] == second.report["selected_parameters"]
    assert first.report["results"]["training"] == second.report["results"]["training"]
    assert first.report["results"]["holdout"] != second.report["results"]["holdout"]


def test_training_outcomes_purged_and_calendar_holdout_aligned_across_symbols(predictable_setups):
    full = evaluation_bars()
    provider = EvaluationProvider({"LONG": full, "SHORT": full.iloc[60:-30].copy()})
    snapshot = protocol.capture_evaluation_snapshot(["LONG", "SHORT", "MISSING"], provider, "2y")
    split = protocol.holdout_start(snapshot, protocol.EvaluationProtocol())
    assert split == full.index[360]
    phases = [protocol.evaluate_phase(snapshot, RectangleScanParameters(), protocol.evaluation_parameters(),
                                      phase=name, split=split) for name in ("training", "holdout")]
    for phase, name in zip(phases, ("training", "holdout")):
        assert phase.result.total_symbols == 3
        assert phase.result.failed_symbols == ["MISSING"]
        assert any("Incomplete" in warning for warning in phase.warnings)
        for item in phase.result.results:
            bars = snapshot.bars_by_symbol[item.symbol]
            assert item.total_trades > 0
            for trade in item.trades:
                if name == "training":
                    assert bars.index[trade.signal_index] < split
                    assert bars.index[trade.entry_index] < split
                    assert bars.index[trade.exit_index] < split
                else:
                    assert bars.index[trade.signal_index] >= split
    pd.testing.assert_frame_equal(snapshot.bars_by_symbol["LONG"], full)


def test_short_missing_and_empty_history_not_counted_as_evaluated():
    provider = EvaluationProvider({"SHORT": evaluation_bars(220), "EMPTY": pd.DataFrame()})
    snapshot = protocol.capture_evaluation_snapshot(["SHORT", "EMPTY", "MISSING"], provider, "2y")
    report = evaluate_fixed_snapshot(fixed_spec(snapshot.symbols), snapshot)
    heldout = report["results"]["holdout"]
    assert heldout["result"]["results"] == []
    assert heldout["result"]["total_symbols"] == 3
    assert len(heldout["result"]["failed_symbols"]) == 3
    assert heldout["mean_net_trade_return"] is None
    assert heldout["target_hit_rate"] is None
    assert any("Small holdout sample" in warning for warning in heldout["warnings"])
    assert "private provider response" not in str(report)


def test_zero_training_trades_skip_holdout_entirely(monkeypatch):
    calls = []
    def no_setup(symbol, history, parameters):
        calls.append(history.index[-1])
        raise ValueError("No setup")
    monkeypatch.setattr(engine, "analyze_rectangle", no_setup)
    bars = evaluation_bars()
    result = compare_rectangle_strategies(["TEST"], EvaluationProvider({"TEST": bars}),
                                          period="2y", scan_parameters=RectangleScanParameters())
    assert len(result.rows) == 12
    assert result.report["selected_parameters"] is None
    assert result.report["results"]["holdout"] is None
    assert max(calls) < bars.index[360]
    assert "Best current" not in result.recommendation
    assert all("Promising" not in row["label"] for row in result.rows)


def test_selection_and_holdout_replay_from_embedded_bars_without_provider(predictable_setups):
    provider = EvaluationProvider({"TEST": evaluation_bars()})
    result = compare_rectangle_strategies(["TEST", "MISSING"], provider, period="2y",
                                          scan_parameters=RectangleScanParameters())
    replay = replay_evaluation_report(result.report)
    assert replay["results"] == result.report["results"]
    assert replay["report_id"] == result.report["report_id"]
    assert provider.calls == ["MISSING", "TEST"]


@pytest.mark.parametrize("field", ["fee_bps_per_side", "slippage_bps_per_side"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), 1001])
def test_evaluation_rejects_invalid_costs(field, value):
    with pytest.raises(ValueError):
        protocol.evaluation_parameters(**{field: value})
