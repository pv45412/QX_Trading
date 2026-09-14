"""Unit tests for QX Advanced Backtesting & Walk-Forward Engine."""

from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
import pytest

from qx.backtesting import (
    EvaluationProtocol,
    WalkForwardConfig,
    WalkForwardFold,
    backtest_rectangle_breakouts,
    build_evaluation_report,
    build_walk_forward_folds,
)


def _generate_synthetic_bars(num_bars: int = 300) -> pd.DataFrame:
    """Generate synthetic OHLCV price bar DataFrame for testing."""
    np.random.seed(42)
    start_date = datetime(2025, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(num_bars)]

    close = 100.0 + np.cumsum(np.random.randn(num_bars) * 1.5)
    close = np.maximum(10.0, close)
    high = close + np.random.rand(num_bars) * 2.0
    low = close - np.random.rand(num_bars) * 2.0
    open_p = low + np.random.rand(num_bars) * (high - low)
    volume = np.random.randint(100000, 5000000, size=num_bars)

    df = pd.DataFrame(
        {
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=pd.DatetimeIndex(dates),
    )
    return df


def test_walk_forward_fold_generation():
    """Verify leak-free chronological fold splits with WalkForwardConfig."""
    config = WalkForwardConfig(
        initial_train_sessions=100,
        holdout_sessions=20,
        step_sessions=20,
        embargo_sessions=5,
    )
    labels = [date(2025, 1, 1) + timedelta(days=i) for i in range(200)]
    as_of = date(2025, 1, 1) + timedelta(days=200)
    folds = build_walk_forward_folds(labels, config, as_of_date=as_of)

    assert len(folds) >= 1
    fold1 = folds[0]
    assert isinstance(fold1, WalkForwardFold)
    assert fold1.fold_number == 1
    assert len(fold1.train_indices) == 100
    assert len(fold1.embargo_indices) == 5
    assert len(fold1.holdout_indices) == 20


def test_backtest_rectangle_breakouts_synthetic():
    """Verify historical backtest execution on synthetic bar data."""
    bars = _generate_synthetic_bars(num_bars=350)
    result = backtest_rectangle_breakouts(symbol="TEST", bars=bars)

    assert result.symbol == "TEST"
    assert result.total_trades >= 0
    assert 0.0 <= result.win_rate <= 1.0


def test_backtesting_package_exports():
    """Verify public symbols are accessible via qx.backtesting package."""
    assert callable(backtest_rectangle_breakouts)
    assert callable(build_walk_forward_folds)
    assert WalkForwardConfig is not None
    assert WalkForwardFold is not None
    assert EvaluationProtocol is not None
    assert callable(build_evaluation_report)
