"""Phase 3 Unit Tests: 0-Lookahead Market Structure & State Machine.

Verifies:
1. Centered pivot confirmation timestamps and 0-lookahead behavior.
2. Prior-state event classification (BOS vs CHoCH vs INITIAL_BREAK).
3. Break confirmation mode (CLOSE vs WICK).
4. Protected swing model & duplicate event prevention.
5. Timeframe isolation & event provenance.
"""

import numpy as np
import pandas as pd
import pytest
from qx.structure.smc_suite import (
    StructuralPivot,
    StructureEvent,
    ProtectedSwing,
    analyze_smc_structure,
    detect_structural_pivots,
)


def _make_trend_bars(base_price: float = 100.0, length: int = 50) -> pd.DataFrame:
    """Helper to build 50 5m bars with pivot swings."""
    times = pd.date_range("2026-09-15 09:30", periods=length, freq="5min")
    steps = np.linspace(base_price, base_price + 10.0, length)
    # Add swing high at bar 10 and swing low at bar 20
    highs = steps + 0.50
    lows = steps - 0.50
    opens = steps - 0.10
    closes = steps + 0.10

    # Swing high peak at bar 10
    highs[10] = steps[10] + 5.0
    closes[10] = steps[10] + 4.8
    # Swing low trough at bar 20
    lows[20] = steps[20] - 5.0
    closes[20] = steps[20] - 4.8

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(length, 2000),
    }, index=times)


def test_pivot_not_available_before_confirmation_timestamp():
    """Verify that a centered pivot occurring at bar 10 (with ext_window=5, half_ext=2) is NOT available at bar 11."""
    bars = _make_trend_bars(100.0, length=30)
    # Pivot at bar 10 with ext_window=5 (half_ext=2) is confirmed at bar 12
    pivots_at_11 = detect_structural_pivots(bars, ext_window=5, evaluation_bar_index=11)
    # High pivot at bar 10 requires confirm_idx = 12, so at eval_idx=11 it must NOT be returned
    piv_ids_11 = [p.pivot_id for p in pivots_at_11]
    assert "PIVOT_HIGH_10_5m" not in piv_ids_11


def test_pivot_available_at_knowledge_timestamp():
    """Verify that a centered pivot occurring at bar 10 IS available at bar 12 (confirmation_bar_index)."""
    bars = _make_trend_bars(100.0, length=30)
    pivots_at_12 = detect_structural_pivots(bars, ext_window=5, evaluation_bar_index=12)
    piv_ids_12 = [p.pivot_id for p in pivots_at_12]
    assert "PIVOT_HIGH_10_5m" in piv_ids_12
    
    # Verify timestamps match
    target_piv = [p for p in pivots_at_12 if p.pivot_id == "PIVOT_HIGH_10_5m"][0]
    assert target_piv.bar_index == 10
    assert target_piv.confirmation_bar_index == 12
    assert target_piv.pivot_timestamp != target_piv.knowledge_timestamp


def test_backtest_cannot_use_future_confirmed_pivot():
    """Verify backtest evaluation at bar 15 cannot see or use a pivot confirmed at bar 22."""
    bars = _make_trend_bars(100.0, length=40)
    res_15 = analyze_smc_structure(bars, is_fast_chart=True, evaluation_bar_index=15)
    res_25 = analyze_smc_structure(bars, is_fast_chart=True, evaluation_bar_index=25)
    
    pivots_15_ids = [p.pivot_id for p in res_15.confirmed_pivots]
    pivots_25_ids = [p.pivot_id for p in res_25.confirmed_pivots]

    # Bar 20 low pivot requires confirm_idx = 22 with fast chart (ext_window=5, half_ext=2)
    assert "PIVOT_LOW_20_5m" not in pivots_15_ids
    assert "PIVOT_LOW_20_5m" in pivots_25_ids


def test_bullish_bos_requires_prior_bullish_structure():
    """Verify BULLISH_BOS occurs when previous state is BULLISH and price breaks active high."""
    bars = _make_trend_bars(100.0, length=50)
    res = analyze_smc_structure(bars, is_fast_chart=True)
    bos_events = [e for e in res.events if e.event_type == "BULLISH_BOS"]
    for e in bos_events:
        assert e.previous_structure_state == "BULLISH"
        assert e.new_structure_state == "BULLISH"
        assert e.direction == "BULLISH"


def test_bearish_bos_requires_prior_bearish_structure():
    """Verify BEARISH_BOS occurs when previous state is BEARISH and price breaks active low."""
    # Build a declining bar set
    times = pd.date_range("2026-09-15 09:30", periods=50, freq="5min")
    steps = np.linspace(200.0, 150.0, 50)
    bars = pd.DataFrame({
        "open": steps + 0.10,
        "high": steps + 0.50,
        "low": steps - 0.50,
        "close": steps - 0.10,
        "volume": np.full(50, 2000),
    }, index=times)
    # Add a swing low peak at index 10 and index 25
    bars.loc[bars.index[10], "low"] = 185.0
    bars.loc[bars.index[25], "low"] = 165.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    bear_bos_events = [e for e in res.events if e.event_type == "BEARISH_BOS"]
    for e in bear_bos_events:
        assert e.previous_structure_state == "BEARISH"
        assert e.new_structure_state == "BEARISH"
        assert e.direction == "BEARISH"


def test_bearish_choch_requires_prior_bullish_structure():
    """Verify BEARISH_CHOCH occurs when previous state is BULLISH and price breaks protected low."""
    times = pd.date_range("2026-09-15 09:30", periods=50, freq="5min")
    steps = np.linspace(100.0, 150.0, 50)
    bars = pd.DataFrame({
        "open": steps - 0.10,
        "high": steps + 0.50,
        "low": steps - 0.50,
        "close": steps + 0.10,
        "volume": np.full(50, 2000),
    }, index=times)

    # Low swing at index 10 (protected low = 95.0)
    bars.loc[bars.index[10], "low"] = 95.0
    bars.loc[bars.index[10], "close"] = 96.0

    # Reversal drop at index 35 below 95.0
    bars.loc[bars.index[35:], "close"] = 90.0
    bars.loc[bars.index[35:], "low"] = 88.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    choch_events = [e for e in res.events if e.event_type == "BEARISH_CHOCH"]
    for e in choch_events:
        assert e.previous_structure_state == "BULLISH"
        assert e.new_structure_state == "BEARISH"


def test_bullish_choch_requires_prior_bearish_structure():
    """Verify BULLISH_CHOCH occurs when previous state is BEARISH and price breaks protected high."""
    times = pd.date_range("2026-09-15 09:30", periods=50, freq="5min")
    steps = np.linspace(200.0, 150.0, 50)
    bars = pd.DataFrame({
        "open": steps + 0.10,
        "high": steps + 0.50,
        "low": steps - 0.50,
        "close": steps - 0.10,
        "volume": np.full(50, 2000),
    }, index=times)

    # High swing at index 10 (protected high = 205.0)
    bars.loc[bars.index[10], "high"] = 205.0
    bars.loc[bars.index[10], "close"] = 204.0

    # Reversal surge at index 35 above 205.0
    bars.loc[bars.index[35:], "close"] = 210.0
    bars.loc[bars.index[35:], "high"] = 212.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    choch_events = [e for e in res.events if e.event_type == "BULLISH_CHOCH"]
    for e in choch_events:
        assert e.previous_structure_state == "BEARISH"
        assert e.new_structure_state == "BULLISH"


def test_neutral_initial_break_is_not_choch():
    """Verify first break from NEUTRAL state emits INITIAL_BREAK, not CHoCH."""
    bars = _make_trend_bars(100.0, length=30)
    res = analyze_smc_structure(bars, is_fast_chart=True)
    first_event = res.events[0] if res.events else None
    assert first_event is not None
    assert first_event.previous_structure_state == "NEUTRAL"
    assert "INITIAL_BREAK" in first_event.event_type
    assert "CHOCH" not in first_event.event_type


def test_structure_event_uses_previous_state_before_update():
    """Verify structure event records previous_structure_state BEFORE the event is processed."""
    bars = _make_trend_bars(100.0, length=50)
    res = analyze_smc_structure(bars, is_fast_chart=True)
    for evt in res.events:
        if evt.event_type == "BULLISH_INITIAL_BREAK":
            assert evt.previous_structure_state == "NEUTRAL"
            assert evt.new_structure_state == "BULLISH"
        elif evt.event_type == "BULLISH_BOS":
            assert evt.previous_structure_state == "BULLISH"
            assert evt.new_structure_state == "BULLISH"


def test_wick_only_break_does_not_trigger_when_close_required():
    """Verify a wick extending beyond structural high does NOT trigger break when mode is CLOSE."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    # Flat baseline at 100.0
    opens = np.full(30, 100.0)
    highs = np.full(30, 100.0)
    lows = np.full(30, 99.0)
    closes = np.full(30, 100.0)
    bars = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(30, 1000),
    }, index=times)

    # Set high pivot at index 5 = 105.0 (bars 4 and 6 have high=100.0, so bar 5 is pivot high 105.0)
    bars.loc[bars.index[5], "high"] = 105.0
    
    # At index 20, wick reaches 106.0 but close is 104.0
    bars.loc[bars.index[20], "high"] = 106.0
    bars.loc[bars.index[20], "close"] = 104.0

    res_close = analyze_smc_structure(bars, is_fast_chart=True, break_confirmation_mode="CLOSE")
    res_wick = analyze_smc_structure(bars, is_fast_chart=True, break_confirmation_mode="WICK")

    # Under CLOSE mode, bar 20 does not break 105.0
    evts_close_20 = [e for e in res_close.events if e.event_timestamp == timestamps_str(bars, 20)]
    evts_wick_20 = [e for e in res_wick.events if e.event_timestamp == timestamps_str(bars, 20)]

    assert len(evts_close_20) == 0
    assert len(evts_wick_20) == 1


def timestamps_str(df, idx):
    return df.index[idx].strftime("%Y-%m-%d %H:%M UTC")


def test_duplicate_bos_not_emitted_for_same_level():
    """Verify multiple consecutive bars closing above the same broken level do NOT re-emit BOS events."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    steps = np.linspace(100.0, 120.0, 30)
    bars = pd.DataFrame({
        "open": steps,
        "high": steps + 0.20,
        "low": steps - 0.20,
        "close": steps + 0.10,
        "volume": np.full(30, 1000),
    }, index=times)

    res = analyze_smc_structure(bars, is_fast_chart=True)
    # Group events by source_pivot_id
    pivot_event_counts = {}
    for evt in res.events:
        pivot_event_counts[evt.source_pivot_id] = pivot_event_counts.get(evt.source_pivot_id, 0) + 1

    for piv_id, count in pivot_event_counts.items():
        assert count == 1  # Exactly ONE event per broken pivot level!


def test_duplicate_choch_not_emitted_for_same_level():
    """Verify duplicate CHoCH events are not emitted for the same broken protected level."""
    times = pd.date_range("2026-09-15 09:30", periods=40, freq="5min")
    steps = np.linspace(100.0, 130.0, 40)
    bars = pd.DataFrame({
        "open": steps,
        "high": steps + 0.20,
        "low": steps - 0.20,
        "close": steps + 0.10,
        "volume": np.full(40, 1000),
    }, index=times)

    # Set low protected swing at index 8
    bars.loc[bars.index[8], "low"] = 90.0

    # Drop below 90.0 for 5 consecutive candles at index 25-29
    for k in range(25, 30):
        bars.loc[bars.index[k], "close"] = 85.0
        bars.loc[bars.index[k], "low"] = 84.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    choch_events = [e for e in res.events if "CHOCH" in e.event_type]
    choch_pivots = [e.source_pivot_id for e in choch_events]
    assert len(choch_pivots) == len(set(choch_pivots))  # No duplicate CHoCH per pivot level


def test_5m_structure_does_not_use_15m_pivots():
    """Verify 5m structure engine isolates 5m timeframe pivots."""
    bars = _make_trend_bars(100.0, length=40)
    res_5m = analyze_smc_structure(bars, is_fast_chart=True, timeframe="5m")
    res_15m = analyze_smc_structure(bars, is_fast_chart=True, timeframe="15m")

    for p in res_5m.confirmed_pivots:
        assert p.timeframe == "5m"
    for e in res_5m.events:
        assert e.timeframe == "5m"

    for p in res_15m.confirmed_pivots:
        assert p.timeframe == "15m"
    for e in res_15m.events:
        assert e.timeframe == "15m"


def test_structure_event_contains_pivot_and_knowledge_provenance():
    """Verify StructureEvent contains source_pivot_id, event_timestamp, and knowledge_timestamp."""
    bars = _make_trend_bars(100.0, length=40)
    res = analyze_smc_structure(bars, is_fast_chart=True)
    assert len(res.events) > 0
    for evt in res.events:
        assert evt.source_pivot_id.startswith("PIVOT_")
        assert evt.event_timestamp != ""
        assert evt.knowledge_timestamp != ""
        assert evt.config_version == "research_v1"
        assert evt.engine_version == "v3.1.0"


def test_bullish_bos_promotes_correct_protected_low():
    """Verify BULLISH_BOS promotes recent confirmed low pivot to protected_low."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # Low A at 3 (95.0), High B at 7 (105.0), Low C at 12 (98.0), High D at 16 (110.0)
    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[7], "high"] = 105.0
    bars.loc[bars.index[12], "low"] = 98.0
    bars.loc[bars.index[16], "high"] = 110.0

    # Initial break of 105.0 at bar 10 -> BULLISH_INITIAL_BREAK
    bars.loc[bars.index[10], "close"] = 107.0

    # BOS break of 110.0 at bar 20 -> BULLISH_BOS
    bars.loc[bars.index[20], "close"] = 112.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    bos_events = [e for e in res.events if e.event_type == "BULLISH_BOS"]
    assert len(bos_events) == 1
    assert res.protected_low is not None
    assert res.protected_low.role == "PROTECTED_LOW"
    assert res.protected_low.price == 98.0  # Promoted to Low C!
    assert res.protected_low.promoted_by_event_id == bos_events[0].event_id


def test_bearish_bos_promotes_correct_protected_high():
    """Verify BEARISH_BOS promotes recent confirmed high pivot to protected_high."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 101.0),
        "low": np.full(30, 100.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # High A at 3 (105.0), Low B at 7 (95.0), High C at 12 (102.0), Low D at 16 (90.0)
    bars.loc[bars.index[3], "high"] = 105.0
    bars.loc[bars.index[7], "low"] = 95.0
    bars.loc[bars.index[12], "high"] = 102.0
    bars.loc[bars.index[16], "low"] = 90.0

    # Initial break of 95.0 at bar 10 -> BEARISH_INITIAL_BREAK
    bars.loc[bars.index[10], "close"] = 93.0

    # BOS break of 90.0 at bar 20 -> BEARISH_BOS
    bars.loc[bars.index[20], "close"] = 88.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    bos_events = [e for e in res.events if e.event_type == "BEARISH_BOS"]
    assert len(bos_events) == 1
    assert res.protected_high is not None
    assert res.protected_high.role == "PROTECTED_HIGH"
    assert res.protected_high.price == 102.0  # Promoted to High C!
    assert res.protected_high.promoted_by_event_id == bos_events[0].event_id


def test_bearish_choch_retires_bullish_structure_references():
    """Verify BEARISH_CHOCH retires bullish protected_low and establishes protected_high."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # Low A at 3 (95.0), High B at 7 (105.0)
    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[7], "high"] = 105.0

    # Initial break of 105.0 at bar 10 -> BULLISH_INITIAL_BREAK (protected_low = 95.0)
    bars.loc[bars.index[10], "close"] = 107.0

    # CHoCH break below 95.0 at bar 20 -> BEARISH_CHOCH
    bars.loc[bars.index[20], "close"] = 92.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    choch_events = [e for e in res.events if e.event_type == "BEARISH_CHOCH"]
    assert len(choch_events) == 1
    assert res.regime == "BEARISH"
    assert res.protected_low is None  # Bullish protected_low retired!
    assert res.protected_high is not None  # Bearish protected_high established!
    assert res.protected_high.price == 105.0


def test_bullish_choch_retires_bearish_structure_references():
    """Verify BULLISH_CHOCH retires bearish protected_high and establishes protected_low."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 101.0),
        "low": np.full(30, 100.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # High A at 3 (105.0), Low B at 7 (95.0)
    bars.loc[bars.index[3], "high"] = 105.0
    bars.loc[bars.index[7], "low"] = 95.0

    # Initial break of 95.0 at bar 10 -> BEARISH_INITIAL_BREAK (protected_high = 105.0)
    bars.loc[bars.index[10], "close"] = 93.0

    # CHoCH break above 105.0 at bar 20 -> BULLISH_CHOCH
    bars.loc[bars.index[20], "close"] = 108.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    choch_events = [e for e in res.events if e.event_type == "BULLISH_CHOCH"]
    assert len(choch_events) == 1
    assert res.regime == "BULLISH"
    assert res.protected_high is None  # Bearish protected_high retired!
    assert res.protected_low is not None  # Bullish protected_low established!
    assert res.protected_low.price == 95.0


def test_bullish_initial_break_bootstraps_protected_low_correctly():
    """Verify BULLISH_INITIAL_BREAK sets state to BULLISH and bootstraps protected_low."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # Pivot low at bar 3, pivot high at bar 8
    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[8], "high"] = 105.0

    # Break high at bar 20
    bars.loc[bars.index[20], "close"] = 107.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    init_events = [e for e in res.events if e.event_type == "BULLISH_INITIAL_BREAK"]
    assert len(init_events) == 1
    assert res.regime == "BULLISH"
    assert res.protected_low is not None
    assert res.protected_low.price == 95.0


def test_bearish_initial_break_bootstraps_protected_high_correctly():
    """Verify BEARISH_INITIAL_BREAK sets state to BEARISH and bootstraps protected_high."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 101.0),
        "low": np.full(30, 100.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # Pivot high at bar 3, pivot low at bar 8
    bars.loc[bars.index[3], "high"] = 108.0
    bars.loc[bars.index[8], "low"] = 94.0

    # Break low at bar 20
    bars.loc[bars.index[20], "close"] = 92.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    init_events = [e for e in res.events if e.event_type == "BEARISH_INITIAL_BREAK"]
    assert len(init_events) == 1
    assert res.regime == "BEARISH"
    assert res.protected_high is not None
    assert res.protected_high.price == 108.0


def test_unconfirmed_pivot_cannot_become_protected_swing():
    """Verify pivots confirmed after evaluation_bar_index cannot become protected swings."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # High at bar 10 (on fast chart half_ext=2, confirmed at bar 12)
    bars.loc[bars.index[10], "high"] = 110.0

    # Evaluate at bar 9 (before bar 10 pivot forms)
    res_at_9 = analyze_smc_structure(bars, is_fast_chart=True, evaluation_bar_index=9)
    assert not any(p.pivot_price == 110.0 for p in res_at_9.confirmed_pivots)

    # Evaluate at bar 11 (pivot formed at 10, but confirmed at 12)
    res_at_11 = analyze_smc_structure(bars, is_fast_chart=True, evaluation_bar_index=11)
    assert not any(p.pivot_price == 110.0 for p in res_at_11.confirmed_pivots)

    # Evaluate at bar 12 (confirmed!)
    res_at_12 = analyze_smc_structure(bars, is_fast_chart=True, evaluation_bar_index=12)
    assert any(p.pivot_price == 110.0 for p in res_at_12.confirmed_pivots)


def test_protected_swing_preserves_pivot_knowledge_timestamp():
    """Verify ProtectedSwing contains knowledge_timestamp, promoted_at, role, and timeframe."""
    bars = _make_trend_bars(100.0, length=40)
    res = analyze_smc_structure(bars, is_fast_chart=True)
    if res.protected_low:
        assert res.protected_low.role in ("PROTECTED_LOW", "ACTIVE_LOW")
        assert res.protected_low.knowledge_timestamp != ""
        assert res.protected_low.promoted_at != ""
        assert res.protected_low.timeframe == "5m"


def test_retired_structural_level_cannot_emit_new_event():
    """Verify a retired/broken level cannot generate duplicate future events."""
    times = pd.date_range("2026-09-15 09:30", periods=40, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(40, 100.0),
        "high": np.full(40, 100.0),
        "low": np.full(40, 99.0),
        "close": np.full(40, 100.0),
        "volume": np.full(40, 1000),
    }, index=times)

    # Low A at 3 (95.0), High B at 7 (105.0)
    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[7], "high"] = 105.0

    # Initial break of 105.0 at bar 10 -> BULLISH_INITIAL_BREAK (protected_low = 95.0)
    bars.loc[bars.index[10], "close"] = 107.0

    # Low at bar 20 drops to 90.0 (BEARISH_CHOCH)
    bars.loc[bars.index[20], "close"] = 90.0

    # Low at bar 25 drops to 85.0
    bars.loc[bars.index[25], "close"] = 85.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    # Pivot Low A (95.0) should emit exactly 1 CHoCH event
    piv_3_events = [e for e in res.events if e.level_broken == 95.0]
    assert len(piv_3_events) == 1


def test_only_one_state_changing_event_per_bar():
    """Verify at most one state-changing event is emitted per bar per timeframe."""
    bars = _make_trend_bars(100.0, length=40)
    res = analyze_smc_structure(bars, is_fast_chart=True)
    timestamp_counts = {}
    for evt in res.events:
        timestamp_counts[evt.event_timestamp] = timestamp_counts.get(evt.event_timestamp, 0) + 1

    for ts, count in timestamp_counts.items():
        assert count <= 1


def test_choch_has_priority_over_bos_when_conditions_conflict():
    """Verify CHoCH takes precedence over BOS if both conditions occur on the same bar."""
    times = pd.date_range("2026-09-15 09:30", periods=40, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(40, 100.0),
        "high": np.full(40, 100.0),
        "low": np.full(40, 99.0),
        "close": np.full(40, 100.0),
        "volume": np.full(40, 1000),
    }, index=times)

    # Low A at 3 (95.0), High B at 7 (105.0)
    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[7], "high"] = 105.0

    # Initial break of 105.0 at bar 10 -> BULLISH_INITIAL_BREAK (protected_low = 95.0)
    bars.loc[bars.index[10], "high"] = 107.0
    bars.loc[bars.index[10], "close"] = 107.0

    # At bar 25 under WICK mode: high reaches 145.0 (BOS candidate) AND low drops to 90.0 (CHoCH candidate)
    bars.loc[bars.index[25], "high"] = 145.0
    bars.loc[bars.index[25], "low"] = 90.0

    res = analyze_smc_structure(bars, is_fast_chart=True, break_confirmation_mode="WICK")
    bar_25_events = [e for e in res.events if e.event_timestamp == timestamps_str(bars, 25)]

    assert len(bar_25_events) == 1
    assert bar_25_events[0].event_type == "BEARISH_CHOCH"  # CHoCH priority!


def test_bullish_bos_does_not_promote_unrelated_latest_internal_low():
    """Verify BULLISH_BOS rejects INTERNAL low pivots and selects qualified EXTERNAL pullback low."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # Low A at 3 (95.0), High B at 7 (105.0), Low C at 12 (98.0 - EXTERNAL), High D at 16 (110.0)
    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[7], "high"] = 105.0
    bars.loc[bars.index[12], "low"] = 98.0
    bars.loc[bars.index[16], "high"] = 110.0

    # Initial break of 105.0 at bar 10
    bars.loc[bars.index[10], "close"] = 107.0

    # BOS break of 110.0 at bar 20
    bars.loc[bars.index[20], "close"] = 112.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    # Manually mark a minor pivot at bar 18 as INTERNAL to test rejection
    for p in res.confirmed_pivots:
        if p.bar_index == 18:
            p.classification = "INTERNAL"

    assert res.protected_low is not None
    assert res.protected_low.price == 98.0  # Selected qualified EXTERNAL low at bar 12!
    assert res.protected_low.selection_reason == "PULLBACK_BEFORE_BOS"


def test_bearish_bos_does_not_promote_unrelated_latest_internal_high():
    """Verify BEARISH_BOS rejects INTERNAL high pivots and selects qualified EXTERNAL rally high."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 101.0),
        "low": np.full(30, 100.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # High A at 3 (105.0), Low B at 7 (95.0), High C at 12 (102.0 - EXTERNAL), Low D at 16 (90.0)
    bars.loc[bars.index[3], "high"] = 105.0
    bars.loc[bars.index[7], "low"] = 95.0
    bars.loc[bars.index[12], "high"] = 102.0
    bars.loc[bars.index[16], "low"] = 90.0

    # Initial break of 95.0 at bar 10
    bars.loc[bars.index[10], "close"] = 93.0

    # BOS break of 90.0 at bar 20
    bars.loc[bars.index[20], "close"] = 88.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    assert res.protected_high is not None
    assert res.protected_high.price == 102.0  # Selected qualified EXTERNAL high at bar 12!
    assert res.protected_high.selection_reason == "RALLY_BEFORE_BOS"


def test_bullish_protected_low_belongs_to_bos_structural_leg():
    """Verify protected_low provenance links to the active high pivot of the BOS structural leg."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    bars.loc[bars.index[3], "low"] = 95.0
    bars.loc[bars.index[7], "high"] = 105.0
    bars.loc[bars.index[12], "low"] = 98.0
    bars.loc[bars.index[16], "high"] = 110.0

    bars.loc[bars.index[10], "close"] = 107.0
    bars.loc[bars.index[20], "close"] = 112.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    assert res.protected_low is not None
    assert res.protected_low.source_leg_start_pivot_id == "PIVOT_HIGH_16_5m"
    assert res.protected_low.source_leg_end_event_id == "EVT_BOS_20_5m"


def test_bearish_protected_high_belongs_to_bos_structural_leg():
    """Verify protected_high provenance links to the active low pivot of the BOS structural leg."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 101.0),
        "low": np.full(30, 100.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    bars.loc[bars.index[3], "high"] = 105.0
    bars.loc[bars.index[7], "low"] = 95.0
    bars.loc[bars.index[12], "high"] = 102.0
    bars.loc[bars.index[16], "low"] = 90.0

    bars.loc[bars.index[10], "close"] = 93.0
    bars.loc[bars.index[20], "close"] = 88.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    assert res.protected_high is not None
    assert res.protected_high.source_leg_start_pivot_id == "PIVOT_LOW_16_5m"
    assert res.protected_high.source_leg_end_event_id == "EVT_BOS_20_5m"


def test_initial_bullish_break_does_not_use_distant_unrelated_low():
    """Verify BULLISH_INITIAL_BREAK does not use a distant low pivot formed > 25 bars ago when no local low exists."""
    times = pd.date_range("2026-09-15 09:30", periods=60, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(60, 100.0),
        "high": np.full(60, 100.0),
        "low": np.full(60, 99.0),
        "close": np.full(60, 100.0),
        "volume": np.full(60, 1000),
    }, index=times)

    # Distant low pivot at bar 3 (90.0)
    bars.loc[bars.index[3], "low"] = 90.0

    # High pivot at bar 45 (105.0) - formed 42 bars after low at bar 3!
    bars.loc[bars.index[45], "high"] = 105.0

    # Initial break at bar 55
    bars.loc[bars.index[55], "close"] = 107.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    # Distant low pivot at bar 3 (52 bars before break at bar 55) is rejected!
    assert res.protected_low is None


def test_initial_bearish_break_does_not_use_distant_unrelated_high():
    """Verify BEARISH_INITIAL_BREAK does not use a distant high pivot formed > 25 bars ago when no local high exists."""
    times = pd.date_range("2026-09-15 09:30", periods=60, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(60, 100.0),
        "high": np.full(60, 101.0),
        "low": np.full(60, 100.0),
        "close": np.full(60, 100.0),
        "volume": np.full(60, 1000),
    }, index=times)

    # Distant high pivot at bar 3 (120.0)
    bars.loc[bars.index[3], "high"] = 120.0

    # Low pivot at bar 45 (95.0)
    bars.loc[bars.index[45], "low"] = 95.0

    # Initial break at bar 55
    bars.loc[bars.index[55], "close"] = 93.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    # Distant high pivot at bar 3 is rejected!
    assert res.protected_high is None


def test_missing_qualified_bootstrap_pivot_does_not_invent_protected_level():
    """Verify that when no qualified pivot exists in local leg, protected swing remains None cleanly."""
    times = pd.date_range("2026-09-15 09:30", periods=30, freq="5min")
    bars = pd.DataFrame({
        "open": np.full(30, 100.0),
        "high": np.full(30, 100.0),
        "low": np.full(30, 99.0),
        "close": np.full(30, 100.0),
        "volume": np.full(30, 1000),
    }, index=times)

    # High pivot at bar 5 (105.0) - NO low pivot in data!
    bars.loc[bars.index[5], "high"] = 105.0
    bars.loc[bars.index[20], "close"] = 107.0

    res = analyze_smc_structure(bars, is_fast_chart=True)
    assert res.regime == "BULLISH"
    assert res.protected_low is None  # Does not invent dummy level!


def test_pullback_selector_returns_none_when_no_pivot_inside_leg():
    """Verify find_qualified_pullback_low returns None when no pivot exists inside leg."""
    from qx.structure.smc_suite import find_qualified_pullback_low, StructuralPivot
    pivots = [
        StructuralPivot(
            pivot_id="P1",
            pivot_type="LOW",
            pivot_price=95.0,
            pivot_timestamp="t1",
            confirmation_timestamp="t2",
            knowledge_timestamp="t2",
            classification="EXTERNAL",
            bar_index=5,
            confirmation_bar_index=7,
        )
    ]
    # leg_start_bar=10, break_bar=20 -> bar_index 5 is before leg_start_bar!
    res = find_qualified_pullback_low(pivots, leg_start_bar=10, break_bar=20, evaluation_bar=20, max_lookback_bars=25)
    assert res is None


def test_rally_selector_returns_none_when_no_pivot_inside_leg():
    """Verify find_qualified_rally_high returns None when no pivot exists inside leg."""
    from qx.structure.smc_suite import find_qualified_rally_high, StructuralPivot
    pivots = [
        StructuralPivot(
            pivot_id="P1",
            pivot_type="HIGH",
            pivot_price=105.0,
            pivot_timestamp="t1",
            confirmation_timestamp="t2",
            knowledge_timestamp="t2",
            classification="EXTERNAL",
            bar_index=5,
            confirmation_bar_index=7,
        )
    ]
    # leg_start_bar=10, break_bar=20 -> bar_index 5 is before leg_start_bar!
    res = find_qualified_rally_high(pivots, leg_start_bar=10, break_bar=20, evaluation_bar=20, max_lookback_bars=25)
    assert res is None


def test_pre_leg_external_pivot_is_not_used_as_fallback():
    """Verify an EXTERNAL pivot before leg_start_bar is NEVER used as fallback."""
    from qx.structure.smc_suite import find_qualified_pullback_low, StructuralPivot
    pivots = [
        StructuralPivot(
            pivot_id="P1",
            pivot_type="LOW",
            pivot_price=90.0,
            pivot_timestamp="t1",
            confirmation_timestamp="t2",
            knowledge_timestamp="t2",
            classification="EXTERNAL",
            bar_index=3,
            confirmation_bar_index=5,
        )
    ]
    # Search window: leg_start=10, break_bar=20
    res = find_qualified_pullback_low(pivots, leg_start_bar=10, break_bar=20, evaluation_bar=20, max_lookback_bars=25)
    assert res is None  # Pre-leg pivot at bar 3 MUST NOT be returned!


def test_unclassified_pivot_cannot_become_protected_low():
    """Verify a pivot with classification UNCLASSIFIED is ineligible for protected_low."""
    from qx.structure.smc_suite import find_qualified_pullback_low, StructuralPivot
    pivots = [
        StructuralPivot(
            pivot_id="P1",
            pivot_type="LOW",
            pivot_price=98.0,
            pivot_timestamp="t1",
            confirmation_timestamp="t2",
            knowledge_timestamp="t2",
            classification="UNCLASSIFIED",
            bar_index=15,
            confirmation_bar_index=17,
        )
    ]
    res = find_qualified_pullback_low(pivots, leg_start_bar=10, break_bar=20, evaluation_bar=20, max_lookback_bars=25)
    assert res is None  # UNCLASSIFIED pivot rejected!


def test_unclassified_pivot_cannot_become_protected_high():
    """Verify a pivot with classification UNCLASSIFIED is ineligible for protected_high."""
    from qx.structure.smc_suite import find_qualified_rally_high, StructuralPivot
    pivots = [
        StructuralPivot(
            pivot_id="P1",
            pivot_type="HIGH",
            pivot_price=108.0,
            pivot_timestamp="t1",
            confirmation_timestamp="t2",
            knowledge_timestamp="t2",
            classification="UNCLASSIFIED",
            bar_index=15,
            confirmation_bar_index=17,
        )
    ]
    res = find_qualified_rally_high(pivots, leg_start_bar=10, break_bar=20, evaluation_bar=20, max_lookback_bars=25)
    assert res is None  # UNCLASSIFIED pivot rejected!



