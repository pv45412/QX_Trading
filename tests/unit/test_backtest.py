import pandas as pd
import pytest

from qx.backtesting.engine import (
    backtest_rectangle_breakouts,
    backtest_rectangle_universe,
    sweep_backtest_parameters,
)
from qx.models.backtest import BacktestParameters, BacktestResult, BacktestRunResult, BacktestTrade
from qx.models.market import BarDataRequest
from qx.models.scan import RectangleScanParameters, ScanCandidate
from qx.patterns.rectangle import analyze_rectangle
from qx.ui.pages.backtest import backtest_analytics, backtest_outcome_frame, backtest_trades_frame
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_backtest_runs_without_live_data() -> None:
    bars = _clean_rectangle_bars()

    result = backtest_rectangle_breakouts("TEST", bars)

    assert result.symbol == "TEST"
    assert result.total_trades >= 0
    assert 0 <= result.win_rate <= 1


@pytest.mark.parametrize(
    ("entry_open", "next_open", "next_high", "next_low", "expected_entry", "expected_exit", "outcome"),
    [
        (105.0, 100.0, 106.0, 99.0, 105.0, 100.0, "loss"),
        (100.0, 104.0, 105.0, 95.0, 100.0, 103.0, "win"),
        (100.0, 100.0, 104.0, 96.0, 100.0, 97.0, "loss"),
    ],
)
def test_backtest_gap_fills_and_ambiguous_bars(
    monkeypatch: pytest.MonkeyPatch,
    entry_open: float, next_open: float, next_high: float, next_low: float,
    expected_entry: float, expected_exit: float, outcome: str,
) -> None:
    setup = analyze_rectangle("TEST", _clean_rectangle_bars(), RectangleScanParameters())
    setup = setup.model_copy(update={
        "setup_score": 1.0,
        "metrics": setup.metrics.model_copy(update={"breakout_level": 100.0}),
    })

    def one_signal(symbol: str, history: pd.DataFrame, params: RectangleScanParameters) -> ScanCandidate:
        if len(history) != 201:
            raise ValueError("No setup")
        return setup

    monkeypatch.setattr("qx.backtesting.engine.analyze_rectangle", one_signal)
    bars = pd.DataFrame({
        "open": [100.0] * 210, "high": [101.0] * 210,
        "low": [99.0] * 210, "close": [100.0] * 210, "volume": [1000.0] * 210,
    })
    bars.loc[201, ["open", "high", "low", "close"]] = [entry_open, entry_open + 1, entry_open - 1, entry_open]
    bars.loc[202, ["open", "high", "low", "close"]] = [next_open, next_high, next_low, next_open]
    result = backtest_rectangle_breakouts(
        "TEST", bars, backtest_parameters=BacktestParameters(max_holding_bars=2, entry_window_bars=1),
    )
    assert result.total_trades == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(expected_entry)
    assert trade.exit_price == pytest.approx(expected_exit)
    assert trade.outcome == outcome


def test_backtest_universe_aggregates_symbol_results() -> None:
    result = backtest_rectangle_universe(["TEST"], _StaticProvider())

    assert result.total_symbols == 1
    assert len(result.results) == 1
    assert result.total_trades >= 0
    assert 0 <= result.win_rate <= 1


def test_backtest_parameter_sweep_returns_grid_rows() -> None:
    result = sweep_backtest_parameters(
        ["TEST"],
        _StaticProvider(),
        setup_scores=(0.60, 0.70),
        entry_windows=(3, 5),
    )

    assert len(result) == 4
    assert {"min_setup_score", "entry_window_bars", "trades"}.issubset(result[0])


def test_backtest_analytics_summarizes_trade_quality() -> None:
    result = BacktestRunResult(
        results=[
            BacktestResult(
                symbol="TEST",
                trades=[
                    _trade("TEST", "win", 0.03),
                    _trade("TEST", "loss", -0.02),
                    _trade("TEST", "timeout", 0.01),
                ],
                total_trades=3,
                win_rate=1 / 3,
                average_return_pct=0.01,
            )
        ],
        total_symbols=1,
        total_trades=3,
        win_rate=1 / 3,
        average_return_pct=0.01,
    )

    analytics = backtest_analytics(result)
    outcomes = backtest_outcome_frame(result)
    trades = backtest_trades_frame(result)

    assert analytics["trades"] == 3
    assert analytics["wins"] == 2
    assert analytics["losses"] == 1
    assert analytics["profit_factor"] == 2.0
    assert analytics["expectancy_pct"] > 0
    assert set(outcomes["outcome"]) == {"win", "loss", "timeout"}
    assert len(trades) == 3


def _trade(symbol: str, outcome: str, return_pct: float) -> BacktestTrade:
    return BacktestTrade(
        symbol=symbol,
        signal_index=1,
        entry_index=2,
        entry_price=100.0,
        exit_index=3,
        exit_price=100.0 * (1 + return_pct),
        outcome=outcome,
        return_pct=return_pct,
        setup_score=0.80,
    )


class _StaticProvider:
    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return _clean_rectangle_bars()
