"""Unit tests for Direction composite engine and Volatility EWMA engine."""

import pytest
from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.services.direction_service import DirectionService
from qx.options_scanner.services.volatility_service import VolatilityService


def test_direction_service_bullish_and_bearish():
    config = ScannerConfig()
    ds = DirectionService(config)

    # Strong Bullish case
    res_bull = ds.calculate_direction_score(
        bos_choch=90, vwap=85, ema=80, rvol=80, cum_delta=85, fvg=75, rs=80
    )
    assert res_bull.bias == "BULLISH"
    assert res_bull.score >= 60.0

    # Bearish case
    res_bear = ds.calculate_direction_score(
        bos_choch=20, vwap=15, ema=20, rvol=30, cum_delta=20, fvg=30, rs=25
    )
    assert res_bear.bias == "BEARISH"
    assert res_bear.score <= 40.0


def test_volatility_service_ewma_and_classification():
    config = ScannerConfig()
    vs = VolatilityService(config)

    # 10 synthetic daily return percentages
    returns = [0.012, -0.008, 0.015, -0.005, 0.011, -0.002, 0.009, -0.014, 0.003, 0.007]
    forecast_rv = vs.calculate_ewma_realized_vol(returns)
    assert 0.05 <= forecast_rv <= 0.50

    # CHEAP IV classification
    vol_cheap = vs.calculate_volatility_context(current_iv=0.10, daily_returns=returns)
    assert vol_cheap.classification in ("CHEAP", "FAIR")
    assert vol_cheap.vol_edge < 0.10

    # RICH IV classification
    vol_rich = vs.calculate_volatility_context(current_iv=0.45, daily_returns=returns)
    assert vol_rich.classification == "RICH"
    assert vol_rich.iv_rv_ratio > 1.20
