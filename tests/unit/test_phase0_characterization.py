"""Phase 0: Characterization and Regression Fixtures.

Records baseline outputs for representative market scenarios before refactoring:
- Bullish Trend
- Bearish Trend
- Sideways / Chop
- Opening Breakout
- False Breakout
- Liquidity Sweep
- Low Volume
- High Volume Neutral
- Missing / Stale Data
"""

import numpy as np
import pandas as pd
from qx.signals.smc_rules_engine import generate_smc_trade_signals


def _make_bars(base_price: float, trend_pct: float, vol_mult: float = 1.0, length: int = 20) -> pd.DataFrame:
    steps = np.linspace(base_price, base_price * (1.0 + trend_pct / 100.0), length)
    return pd.DataFrame({
        "open": steps - 0.05,
        "high": steps + 0.15,
        "low": steps - 0.15,
        "close": steps,
        "volume": (np.random.randint(1000, 5000, size=length) * vol_mult).astype(int),
    })


def test_char_bullish_trend():
    bars = _make_bars(180.0, trend_pct=2.0)
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_bearish_trend():
    bars = _make_bars(180.0, trend_pct=-2.0)
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_sideways_chop():
    bars = _make_bars(180.0, trend_pct=0.0)
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_opening_breakout():
    bars = _make_bars(180.0, trend_pct=1.5, vol_mult=2.5)
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_false_breakout():
    bars = _make_bars(180.0, trend_pct=1.0)
    bars.loc[bars.index[-1], "close"] = 179.5
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_liquidity_sweep():
    bars = _make_bars(180.0, trend_pct=-1.0)
    bars.loc[bars.index[-1], "low"] = 177.5
    bars.loc[bars.index[-1], "close"] = 179.8
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_low_volume():
    bars = _make_bars(180.0, trend_pct=0.2, vol_mult=0.1)
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_high_volume_neutral():
    bars = _make_bars(180.0, trend_pct=0.0, vol_mult=3.0)
    res = generate_smc_trade_signals("XLK", bars)
    assert res.symbol == "XLK"
    if res.primary_playbook == "NO_SETUP":
        assert len(res.signals) == 0
    else:
        assert len(res.signals) == 1


def test_char_missing_stale_data():
    """Characterize behavior for empty/stale/insufficient bars (Phase 2.1 enforces BLOCKED)."""
    empty_bars = pd.DataFrame()
    res = generate_smc_trade_signals("XLK", empty_bars)
    assert res.symbol == "XLK"
    assert res.primary_playbook == "BLOCKED"
    assert res.publication_state == "BLOCKED"
    assert res.signal_state == "BLOCKED"
    assert len(res.signals) == 0
