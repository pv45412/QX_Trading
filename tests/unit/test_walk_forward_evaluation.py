from datetime import date

import pandas as pd

from qx.backtesting.walk_forward import WalkForwardConfig
from qx.backtesting.walk_forward_evaluation import evaluate_rectangle_walk_forward
from qx.models.backtest import BacktestParameters, BacktestResult
from qx.models.scan import RectangleScanParameters


def _bars(count: int) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-02", periods=count)
    return pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1_000.0}, index=index)


def test_walk_forward_evaluation_keeps_non_overlapping_holdouts_and_costs(monkeypatch) -> None:
    calls: list[tuple[str, int, float]] = []

    def fake_backtest(symbol, bars, scan_parameters, parameters):
        calls.append((symbol, len(bars), parameters.evaluation_fraction))
        return BacktestResult(symbol=symbol, trades=[], total_trades=0, win_rate=0.0, average_return_pct=0.0)

    monkeypatch.setattr("qx.backtesting.walk_forward_evaluation.backtest_rectangle_breakouts", fake_backtest)
    frame = _bars(12)
    result = evaluate_rectangle_walk_forward(
        {"AAA": frame, "BBB": frame},
        as_of_date=date(2026, 9, 12),
        fold_config=WalkForwardConfig(4, 2, 2, 1),
        scan_parameters=RectangleScanParameters(),
        backtest_parameters=BacktestParameters(fee_bps_per_side=1, slippage_bps_per_side=5),
    )

    assert len(result.folds) == 3
    assert result.costs == {"fee_bps_per_side": 1.0, "slippage_bps_per_side": 5.0}
    assert all(set(left.fold.holdout_dates).isdisjoint(right.fold.holdout_dates) for left, right in zip(result.folds, result.folds[1:]))
    assert any(fraction < 1 for _, _, fraction in calls)


def test_walk_forward_evaluation_uses_only_shared_symbol_sessions() -> None:
    first = _bars(8)
    second = _bars(8).iloc[1:]
    result = evaluate_rectangle_walk_forward(
        {"AAA": first, "BBB": second},
        as_of_date=date(2026, 9, 12),
        fold_config=WalkForwardConfig(4, 2, 2),
        scan_parameters=RectangleScanParameters(),
        backtest_parameters=BacktestParameters(),
    )

    assert result.shared_session_count == 7
    assert result.folds[0].fold.train_dates[0] == second.index[0].date()
