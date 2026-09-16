"""Phase 4: Deterministic, Auditable Order Block Engine Unit Tests.

Verifies:
1. Candidate origin rule (opposite candle in structural leg prior to displacement).
2. Structural consequence requirement (BOS / CHoCH / INITIAL_BREAK mandatory for validation).
3. Displacement evaluation (min_displacement_atr >= 1.0 or min_body_multiplier >= 1.5).
4. Order block state transitions (CANDIDATE, VALIDATED, MITIGATED, INVALIDATED, EXPIRED).
5. Zone boundary construction (BODY_TO_EXTREME default).
6. Fair Value Gap (FVG) quality factor recording.
7. Mitigation count, timestamps, and depth percentage tracking.
8. Invalidation rule (CLOSE_BEYOND_DISTAL).
9. Expiration handling (max_age_bars).
10. Zero-lookahead knowledge time safety.
"""

import pytest
import numpy as np
import pandas as pd
from qx.structure.smc_suite import (
    OrderBlock,
    SMCAnalysisResult,
    StructureEvent,
    analyze_smc_structure,
    extract_and_validate_order_block,
    update_order_block_lifecycles,
    compute_atr_series,
)


def _make_bullish_ob_scenario(base_price: float = 100.0) -> pd.DataFrame:
    """Construct 30 bars producing a clean Bullish Initial Break and Validated Bullish OB at bar 15."""
    n = 30
    prices = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)

    # Leg 1: 0..10 (rise to high pivot at 10)
    prices[0:11] = np.linspace(base_price, base_price + 3.0, 11)
    # Leg 2: 11..15 (pullback to low at 15)
    prices[11:16] = np.linspace(base_price + 2.8, base_price + 1.0, 5)
    # Leg 3: 16..29 (breakout)
    prices[16:n] = np.linspace(base_price + 1.5, base_price + 8.0, n - 16)

    for i in range(n):
        opens[i] = prices[i] - 0.10
        closes[i] = prices[i] + 0.10
        highs[i] = max(opens[i], closes[i]) + 0.15
        lows[i] = min(opens[i], closes[i]) - 0.15

    # High pivot peak at bar 10
    highs[10] = base_price + 3.50
    closes[10] = base_price + 3.20

    # Bearish candidate candle at bar 15
    opens[15] = base_price + 1.40
    closes[15] = base_price + 0.90
    lows[15] = base_price + 0.70
    highs[15] = base_price + 1.50

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(n, 2500),
    })


def _make_bearish_ob_scenario(base_price: float = 200.0) -> pd.DataFrame:
    """Construct 30 bars producing a clean Bearish Initial Break and Validated Bearish OB at bar 15."""
    n = 30
    prices = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)

    # Leg 1: 0..10 (drop to low pivot at 10)
    prices[0:11] = np.linspace(base_price, base_price - 3.0, 11)
    # Leg 2: 11..15 (rally to high at 15)
    prices[11:16] = np.linspace(base_price - 2.8, base_price - 1.0, 5)
    # Leg 3: 16..29 (breakdown)
    prices[16:n] = np.linspace(base_price - 1.5, base_price - 8.0, n - 16)

    for i in range(n):
        opens[i] = prices[i] + 0.10
        closes[i] = prices[i] - 0.10
        highs[i] = max(opens[i], closes[i]) + 0.15
        lows[i] = min(opens[i], closes[i]) - 0.15

    # Low pivot trough at bar 10
    lows[10] = base_price - 3.50
    closes[10] = base_price - 3.20

    # Bullish candidate candle at bar 15
    opens[15] = base_price - 1.40
    closes[15] = base_price - 0.90
    highs[15] = base_price - 0.70
    lows[15] = base_price - 1.50

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(n, 2500),
    })


# --- 1. CANDIDATE ORIGIN RULE ---

def test_candidate_origin_requires_opposite_candle_in_structural_leg():
    """Verify Bullish OB uses candidate bearish candle (c <= o) in the structural leg."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    assert res.demand_ob is not None
    assert res.demand_ob.direction == "BULLISH_ORDER_BLOCK"
    assert res.demand_ob.candidate_bar_index == 15
    # Candidate bar 15 was a red candle (c[15] <= o[15])
    assert bars["close"].iloc[15] <= bars["open"].iloc[15]


def test_bearish_candidate_origin_uses_bullish_candle():
    """Verify Bearish OB uses candidate bullish candle (c >= o) in the structural leg."""
    bars = _make_bearish_ob_scenario(200.0)
    res = analyze_smc_structure(bars)

    assert res.supply_ob is not None
    assert res.supply_ob.direction == "BEARISH_ORDER_BLOCK"
    assert res.supply_ob.candidate_bar_index == 15
    # Candidate bar 15 was a green candle (c[15] >= o[15])
    assert bars["close"].iloc[15] >= bars["open"].iloc[15]


# --- 2. STRUCTURAL CONSEQUENCE IS MANDATORY ---

def test_structural_consequence_is_mandatory_for_validation():
    """Verify that featureless bars with no structural events emit zero VALIDATED Order Blocks."""
    steps = np.linspace(100.0, 100.5, 25)
    plain_bars = pd.DataFrame({
        "open": steps,
        "high": steps + 0.10,
        "low": steps - 0.10,
        "close": steps + 0.05,
        "volume": np.full(25, 1000),
    })

    res = analyze_smc_structure(plain_bars)
    assert len(res.events) == 0
    assert res.demand_ob is None
    assert res.supply_ob is None
    assert len(res.order_blocks) == 0


# --- 3. DISPLACEMENT REQUIREMENT ---

def test_displacement_threshold_evaluation():
    """Verify displacement ATR and body multiplier are recorded in Order Block evidence ladder."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    ob = res.demand_ob
    assert ob is not None
    assert ob.state == "VALIDATED"
    assert ob.displacement_atr > 1.0 or ob.body_multiplier >= 1.5
    assert "displacement_atr" in ob.evidence_ladder
    assert "body_multiplier" in ob.evidence_ladder


# --- 4. ORDER BLOCK STATES ---

def test_order_block_states_lifecycle():
    """Verify explicit lifecycle state machine: CANDIDATE, VALIDATED, MITIGATED, INVALIDATED, EXPIRED."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    assert len(res.order_blocks) > 0
    ob = res.order_blocks[0]
    assert ob.state in ("CANDIDATE", "VALIDATED", "MITIGATED", "INVALIDATED", "EXPIRED")
    assert ob.order_block_id.startswith("OB_BULL_")
    assert ob.config_version == "research_v1"
    assert ob.engine_version == "v4.1.0"


# --- 5. ZONE BOUNDARIES (BODY_TO_EXTREME) ---

def test_zone_construction_body_to_extreme():
    """Verify BODY_TO_EXTREME zone bounds: Bullish proximal=max(o,c), distal=low."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    ob = res.demand_ob
    assert ob is not None
    c15 = bars["close"].iloc[15]
    o15 = bars["open"].iloc[15]
    l15 = bars["low"].iloc[15]

    assert ob.proximal_price == round(max(o15, c15), 2)
    assert ob.distal_price == round(l15, 2)
    assert ob.zone_high == max(ob.proximal_price, ob.distal_price)
    assert ob.zone_low == min(ob.proximal_price, ob.distal_price)


# --- 6. FVG QUALITY FACTOR ---

def test_fvg_created_flag_recorded():
    """Verify FVG creation inside impulse leg is recorded as quality factor without blocking non-FVG blocks."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    ob = res.demand_ob
    assert ob is not None
    assert isinstance(ob.fvg_created, bool)
    if ob.fvg_created:
        assert ob.fvg_id is not None
        assert ob.fvg_id.startswith("FVG_")


# --- 7. MITIGATION RULES ---

def test_mitigation_depth_tracking():
    """Verify price returning into zone transitions state to MITIGATED and tracks depth percentage."""
    bars = _make_bullish_ob_scenario(100.0)
    # Modify bars 25..29 so price retests into proximal boundary of OB (181.4)
    ob_initial = analyze_smc_structure(bars).demand_ob
    prox = ob_initial.proximal_price

    bars_mitigated = bars.copy()
    # Bar 25 dips to prox - 0.20 (into zone)
    bars_mitigated.loc[25, "low"] = prox - 0.20

    res = analyze_smc_structure(bars_mitigated)
    ob = res.demand_ob
    assert ob is not None
    assert ob.state == "MITIGATED"
    assert ob.mitigation_count >= 1
    assert ob.first_mitigation_timestamp is not None
    assert ob.mitigation_depth_pct > 0.0


# --- 8. INVALIDATION RULES ---

def test_invalidation_close_beyond_distal():
    """Verify confirmed close below distal boundary transitions Bullish OB to INVALIDATED."""
    bars = _make_bullish_ob_scenario(100.0)
    ob_initial = analyze_smc_structure(bars).demand_ob
    dist = ob_initial.distal_price

    bars_invalidated = bars.copy()
    # Bar 28 closes below distal boundary
    bars_invalidated.loc[28, "close"] = dist - 0.50

    res = analyze_smc_structure(bars_invalidated)
    # The invalidated block is preserved in order_blocks telemetry
    inval_obs = [ob for ob in res.order_blocks if ob.state == "INVALIDATED"]
    assert len(inval_obs) >= 1
    assert any(ob.order_block_id == ob_initial.order_block_id for ob in inval_obs)
    target_ob = [ob for ob in inval_obs if ob.order_block_id == ob_initial.order_block_id][0]
    assert target_ob.invalidation_timestamp is not None


# --- 9. EXPIRATION RULES ---

def test_order_block_expiration():
    """Verify Order Block transitions to EXPIRED when age_bars exceeds configured max_age_bars."""
    # Create 80 bars to exceed 5m max_age_bars (50)
    base_bars = _make_bullish_ob_scenario(100.0)
    extra_prices = np.linspace(108.0, 115.0, 50)
    extra_df = pd.DataFrame({
        "open": extra_prices,
        "high": extra_prices + 0.20,
        "low": extra_prices - 0.20,
        "close": extra_prices + 0.10,
        "volume": np.full(50, 2000),
    })
    long_bars = pd.concat([base_bars, extra_df], ignore_index=True)

    res = analyze_smc_structure(long_bars, is_fast_chart=True)
    expired_obs = [ob for ob in res.order_blocks if ob.state == "EXPIRED"]
    assert len(expired_obs) >= 1
    assert expired_obs[0].expiration_timestamp is not None


# --- 10. KNOWLEDGE-TIME SAFETY & CANDIDATE AVAILABILITY ---

def test_zero_lookahead_knowledge_time_safety():
    """Verify Order Block knowledge_timestamp equals the structure event confirmation timestamp."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    ob = res.demand_ob
    assert ob is not None
    assert ob.candidate_available_at == "bar_16"
    assert ob.candidate_knowledge_timestamp == "bar_16"
    # Validation knowledge timestamp matches structure event bar timestamp (bar 20)
    assert ob.knowledge_timestamp == "bar_20"
    assert ob.validated_at == "bar_20"


def test_candidate_candle_not_knowable_before_bar_close():
    """Verify candidate_available_at is bar_16 when candidate candle is bar 15."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    ob = res.demand_ob
    assert ob is not None
    assert ob.candidate_bar_index == 15
    assert ob.candidate_timestamp == "bar_15"
    assert ob.candidate_available_at == "bar_16"


# --- 11. VALIDATION-TIME LIFECYCLE CAUSALITY ---

def test_pre_validation_zone_touch_is_not_counted_as_mitigation():
    """Verify a zone touch occurring before structural validation is NOT counted as mitigation."""
    bars = _make_bullish_ob_scenario(100.0)
    # Modify bar 17 (before bar 20 validation event) to touch proximal zone
    ob_initial = analyze_smc_structure(bars).demand_ob
    prox = ob_initial.proximal_price

    bars_pre_touch = bars.copy()
    bars_pre_touch.loc[17, "low"] = prox - 0.10

    # Evaluate up to bar 20 (when validation occurs)
    res = analyze_smc_structure(bars_pre_touch, evaluation_bar_index=20)
    ob = res.demand_ob
    assert ob is not None
    assert ob.state == "VALIDATED"
    assert ob.mitigation_count == 0
    assert ob.first_mitigation_timestamp is None


def test_post_validation_zone_touch_is_counted_as_mitigation():
    """Verify a zone touch occurring after structural validation IS counted as mitigation."""
    bars = _make_bullish_ob_scenario(100.0)
    ob_initial = analyze_smc_structure(bars).demand_ob
    prox = ob_initial.proximal_price

    bars_post_touch = bars.copy()
    # Modify bar 22 (after bar 20 validation event) to touch proximal zone
    bars_post_touch.loc[22, "low"] = prox - 0.10

    res = analyze_smc_structure(bars_post_touch, evaluation_bar_index=25)
    ob = res.demand_ob
    assert ob is not None
    assert ob.state == "MITIGATED"
    assert ob.mitigation_count == 1
    assert ob.first_mitigation_timestamp == "bar_22"


def test_pre_validation_price_action_does_not_retroactively_invalidate_ob():
    """Verify price action before validation bar index does not retroactively invalidate the OB."""
    bars = _make_bullish_ob_scenario(100.0)
    ob_initial = analyze_smc_structure(bars).demand_ob
    dist = ob_initial.distal_price

    bars_pre_inval = bars.copy()
    # Bar 18 drops below distal, but structure break doesn't occur until bar 20
    bars_pre_inval.loc[18, "close"] = dist - 0.50

    res = analyze_smc_structure(bars_pre_inval, evaluation_bar_index=20)
    ob = res.demand_ob
    assert ob is not None
    assert ob.state == "VALIDATED"
    assert ob.invalidation_timestamp is None


# --- 12. TERMINAL STATE IMMUTABILITY & AGE SEMANTICS ---

def test_terminal_state_invalidated_cannot_revert_to_validated():
    """Verify an INVALIDATED Order Block remains INVALIDATED and cannot revert to VALIDATED."""
    bars = _make_bullish_ob_scenario(100.0)
    ob_initial = analyze_smc_structure(bars).demand_ob
    dist = ob_initial.distal_price

    bars_inval = bars.copy()
    bars_inval.loc[22, "close"] = dist - 0.50  # Invalidated at bar 22
    bars_inval.loc[25, "close"] = dist + 5.00  # Price jumps back up at bar 25

    res = analyze_smc_structure(bars_inval, evaluation_bar_index=29)
    inval_obs = [ob for ob in res.order_blocks if ob.order_block_id == ob_initial.order_block_id]
    assert len(inval_obs) == 1
    assert inval_obs[0].state == "INVALIDATED"


def test_terminal_state_expired_cannot_revert_to_validated():
    """Verify an EXPIRED Order Block remains EXPIRED and cannot revert to VALIDATED."""
    base_bars = _make_bullish_ob_scenario(100.0)
    extra_prices = np.linspace(108.0, 115.0, 50)
    extra_df = pd.DataFrame({
        "open": extra_prices,
        "high": extra_prices + 0.20,
        "low": extra_prices - 0.20,
        "close": extra_prices + 0.10,
        "volume": np.full(50, 2000),
    })
    long_bars = pd.concat([base_bars, extra_df], ignore_index=True)

    res = analyze_smc_structure(long_bars, is_fast_chart=True)
    exp_obs = [ob for ob in res.order_blocks if ob.state == "EXPIRED"]
    assert len(exp_obs) >= 1
    exp_ob = exp_obs[0]

    # Verify update_order_block_lifecycles keeps EXPIRED terminal
    atr_series = compute_atr_series(long_bars["high"].to_numpy(), long_bars["low"].to_numpy(), long_bars["close"].to_numpy())
    timestamps = [f"bar_{idx}" for idx in range(len(long_bars))]
    update_order_block_lifecycles([exp_ob], long_bars, atr_series, timestamps, current_bar_idx=75)

    assert exp_ob.state == "EXPIRED"


def test_validation_age_bars_semantics():
    """Verify validation_age_bars measures bars elapsed since validation_bar_index."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars, evaluation_bar_index=25)

    ob = res.demand_ob
    assert ob is not None
    assert ob.validation_bar_index == 20
    assert ob.candidate_bar_index == 15
    assert ob.validation_age_bars == 5  # 25 - 20
    assert ob.candidate_age_bars == 10  # 25 - 15
    assert ob.age_bars == ob.validation_age_bars


# --- 13. BACKWARD COMPATIBILITY PROPERTIES ---

def test_backward_compatibility_properties():
    """Verify block_type, top_price, bottom_price, is_mitigated, bar_index work seamlessly."""
    bars = _make_bullish_ob_scenario(100.0)
    res = analyze_smc_structure(bars)

    ob = res.demand_ob
    assert ob is not None
    assert ob.block_type == "DEMAND_OB"
    assert ob.top_price == ob.zone_high
    assert ob.bottom_price == ob.zone_low
    assert ob.bar_index == ob.candidate_bar_index
    assert ob.is_mitigated is False
