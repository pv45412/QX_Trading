"""Unit tests for QX Unified SMC Rules Engine and Quantitative Modules."""

import numpy as np
import pandas as pd
from qx.structure.smc_suite import analyze_smc_structure
from qx.structure.vscore import calculate_anchored_vscore
from qx.signals.smc_rules_engine import generate_smc_trade_signals


def test_analyze_smc_structure():
    """Test SMC structure analysis on a synthetic 5m bar DataFrame."""
    prices = np.linspace(180.0, 185.0, 25)
    opens = np.where(np.arange(25) % 2 == 0, prices + 0.10, prices - 0.10)
    bars = pd.DataFrame({
        "open": opens,
        "high": prices + 0.25,
        "low": prices - 0.25,
        "close": prices,
        "volume": np.random.randint(1000, 5000, size=25),
    })

    res = analyze_smc_structure(bars)
    assert res.regime in ("BULLISH", "BEARISH", "CONSOLIDATION", "NEUTRAL")
    assert 0.0 <= res.structure_score <= 100.0


def test_calculate_anchored_vscore():
    """Test Anchored VScore calculation."""
    prices = np.linspace(100.0, 105.0, 20)
    bars = pd.DataFrame({
        "open": prices - 0.05,
        "high": prices + 0.20,
        "low": prices - 0.20,
        "close": prices,
        "volume": np.random.randint(2000, 8000, size=20),
    })

    vscore_res = calculate_anchored_vscore(bars)
    assert -4.0 <= vscore_res.vscore <= 4.0
    assert vscore_res.participation_state in ("LOW", "NORMAL", "CONFIRMED", "HIGH")


def test_generate_smc_trade_signals():
    """Test complete signal generation for XLK."""
    prices = np.linspace(183.0, 183.74, 20)
    bars = pd.DataFrame({
        "open": prices - 0.05,
        "high": prices + 0.15,
        "low": prices - 0.15,
        "close": prices,
        "volume": np.random.randint(1500, 6000, size=20),
    })

    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    assert res.price == 183.74
    assert res.primary_playbook == "NO_SETUP"
    assert len(res.signals) == 0
