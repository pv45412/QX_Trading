import pandas as pd
import numpy as np
import pytest
from qx.models.position_advisor import PositionInput, evaluate_position


def _generate_mock_bars(trend: str = "up") -> pd.DataFrame:
    dates = pd.date_range(end="2026-09-13", periods=100, freq="D")
    if trend == "up":
        prices = np.linspace(100.0, 150.0, 100) + np.random.normal(0, 1.0, 100)
    elif trend == "down":
        prices = np.linspace(150.0, 90.0, 100) + np.random.normal(0, 1.0, 100)
    else:
        prices = np.full(100, 120.0) + np.random.normal(0, 1.0, 100)

    df = pd.DataFrame(
        {
            "open": prices - 0.5,
            "high": prices + 1.5,
            "low": prices - 1.5,
            "close": prices,
            "volume": 100000,
        },
        index=dates,
    )
    return df


def test_evaluate_position_hold():
    bars = _generate_mock_bars("up")
    pos = PositionInput(
        symbol="VST",
        position_type="Long Shares",
        entry_price=130.0,
        quantity=100,
        target_price=170.0,
        stop_loss=120.0,
    )
    report = evaluate_position(pos, bars)
    assert report.action_verdict in ["HOLD", "TRIM / TAKE PROFIT"]
    assert report.confidence_score > 0.5
    assert len(report.positive_factors) > 0


def test_evaluate_position_stop_loss_breached():
    bars = _generate_mock_bars("down")
    pos = PositionInput(
        symbol="VST",
        position_type="Long Shares",
        entry_price=140.0,
        quantity=100,
        target_price=180.0,
        stop_loss=110.0,  # Current price near 90 < 110
    )
    report = evaluate_position(pos, bars)
    assert report.action_verdict == "CLOSE / EXIT"
    assert report.confidence_score >= 0.70
    assert any("BREACHED" in factor for factor in report.negative_factors)
