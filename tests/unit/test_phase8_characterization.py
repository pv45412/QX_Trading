"""Phase 8 Characterization Tests: Tradeability Scenarios.

Provides bar-by-bar replay evidence for three playbooks across four scenarios each.

For each scenario, records:
  triggered_at              — when trigger fired (Phase 7)
  tradeability_evaluated_at — when Phase 8 ran
  observed_entry_reference  — actual underlying price (not trigger fill)
  rvol                      — normalized RVOL at evaluation
  delta                     — delta score and provenance
  extension                 — distance from trigger in ATR
  spread                    — bid/ask spread metrics
  R:R                       — to first target and best target
  hard_gate_outcomes        — which gates passed / failed
  participation_score       — 0–100
  tradeability_state        — TRADEABLE / NOT_TRADEABLE / EXPIRED / BLOCKED
  reason_code               — deterministic outcome code
"""

import pytest

from qx.config.rules_config import RulesEngineConfig, TradeabilityConfig
from qx.models.rules import DeltaProvenance, PublicationState
from qx.tradeability import (
    RVOLBaseline,
    TradeabilityContext,
    TradeabilityEngine,
    TradeabilityReasonCode,
    TradeabilityState,
)


# ─── Shared Helpers ───────────────────────────────────────────────────────────

def make_baseline(mean=1000.0, median=950.0, std=200.0, sessions=20, slot="10:25-10:30") -> RVOLBaseline:
    return RVOLBaseline(
        symbol="NVDA",
        timeframe="5m",
        time_slot=slot,
        slot_mean_volume=mean,
        slot_median_volume=median,
        slot_std=std,
        baseline_sessions_used=sessions,
        baseline_computed_at="2026-09-15T10:20:00Z",
    )


def ctx(
    playbook_id="playbook_a_pullback",
    direction="BULLISH",
    trigger_price=95.0,
    invalidation_price=90.0,
    current_price=96.0,
    atr=2.0,
    current_volume=1500.0,
    rvol_baseline=None,
    delta_value=None,
    delta_provenance=DeltaProvenance.UNAVAILABLE,
    structural_targets=None,
    bars_since_trigger=0,
    quote_age_seconds=5.0,
    gap_beyond_trigger=False,
    gap_distance_atr=0.0,
    publication_state=PublicationState.VERIFIED,
    bid=95.95,
    ask=96.05,
    trigger_source_still_valid=True,
    triggered_at="2026-09-15T10:25:00Z",
    evaluated_at="2026-09-15T10:25:30Z",
) -> TradeabilityContext:
    return TradeabilityContext(
        triggered_setup_id=f"{playbook_id}_eval_20260915",
        playbook_id=playbook_id,
        symbol="NVDA",
        timeframe="5m",
        direction=direction,
        trigger_price=trigger_price,
        invalidation_price=invalidation_price,
        trigger_source_still_valid=trigger_source_still_valid,
        current_price=current_price,
        quote_age_seconds=quote_age_seconds,
        bid=bid,
        ask=ask,
        atr=atr,
        current_volume=current_volume,
        rvol_baseline=rvol_baseline or make_baseline(),
        delta_value=delta_value,
        delta_provenance=delta_provenance,
        structural_target_candidates=structural_targets or [105.0],
        gap_beyond_trigger=gap_beyond_trigger,
        gap_distance_atr=gap_distance_atr,
        bars_since_trigger=bars_since_trigger,
        triggered_at=triggered_at,
        evaluation_timestamp=evaluated_at,
        publication_state=publication_state,
    )


def no_min_participation_engine() -> TradeabilityEngine:
    """Engine with min_participation=0 for all playbooks — isolates other gates."""
    cfg = RulesEngineConfig(
        tradeability=TradeabilityConfig(
            min_participation={
                "playbook_a_pullback": 0.0,
                "playbook_b_liquidity_sweep": 0.0,
                "playbook_c_orb_breakout": 0.0,
            }
        )
    )
    return TradeabilityEngine(rules_config=cfg)


# ─── Playbook A: Trend Pullback ───────────────────────────────────────────────

def test_pullback_strong_participation_tradeable():
    """Pullback — strong RVOL and delta → TRADEABLE.

    Scenario:
      triggered_at:            10:25:00
      tradeability_evaluated_at: 10:25:30 (same bar, after close)
      trigger_price:           95.0
      observed_entry_reference: 96.0 (price at evaluation)
      rvol:                    1.8x mean (strong)
      delta:                   +80, ACTUAL_TRADE_AGGRESSOR (full reliability)
      extension:               0.5 ATR (within 1.0 limit)
      spread:                  tight (bid=95.8, ask=96.2)
      R:R:                     to target 105.0 → reward=9, risk=6 → 1.5 ≥ 1.5
      hard_gate_outcomes:      all pass
      participation_score:     high
      tradeability_state:      TRADEABLE
    """
    baseline = make_baseline(mean=1000.0, std=200.0)
    c = ctx(
        playbook_id="playbook_a_pullback",
        trigger_price=95.0, invalidation_price=90.0, current_price=96.0,
        atr=2.0, current_volume=1800.0, rvol_baseline=baseline,
        delta_value=80.0, delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        structural_targets=[105.0],
        bid=95.8, ask=96.2,
    )
    result = TradeabilityEngine().evaluate_tradeability(c)

    assert result.state == TradeabilityState.TRADEABLE
    assert TradeabilityReasonCode.TRADEABLE_ALL_GATES_PASS.value in result.reason_codes
    assert result.rvol_normalized == pytest.approx(1.8, rel=0.05)
    assert result.delta_score > 0
    assert result.extension_atr == pytest.approx(0.5, rel=0.05)
    assert result.risk_reward_to_target1 == pytest.approx(1.5, rel=0.05)
    assert result.liquidity_status in ("TIGHT", "ACCEPTABLE")
    assert result.trade_state == "NONE - OPTIONS EXPRESSION NOT YET EVALUATED"
    assert result.observed_underlying_price == 96.0


def test_pullback_weak_volume_rejected():
    """Pullback — low RVOL below participation minimum → NOT_TRADEABLE.

    Scenario:
      rvol:               0.3x mean (weak) → participation score < minimum (25.0)
      delta:              UNAVAILABLE
      all other gates:    pass
      tradeability_state: NOT_TRADEABLE
      reason_code:        INSUFFICIENT_PARTICIPATION
    """
    baseline = make_baseline(mean=1000.0, std=200.0, sessions=20)
    c = ctx(
        playbook_id="playbook_a_pullback",
        trigger_price=95.0, invalidation_price=90.0, current_price=96.0,
        atr=2.0, current_volume=300.0, rvol_baseline=baseline,  # 0.3x mean
        delta_value=None, delta_provenance=DeltaProvenance.UNAVAILABLE,
        structural_targets=[105.0],
    )
    result = TradeabilityEngine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.INSUFFICIENT_PARTICIPATION.value in result.reason_codes
    assert result.rvol_normalized == pytest.approx(0.3, rel=0.05)


def test_pullback_excessive_extension_rejected():
    """Pullback — price chased 1.2 ATR above trigger → NOT_TRADEABLE.

    Scenario:
      trigger_price:       95.0, atr=2.0, max_ext=1.0
      current_price:       97.5 → extension=(97.5-95.0)/2.0=1.25 > 1.0
      tradeability_state:  NOT_TRADEABLE
      reason_code:         EXCESSIVE_EXTENSION
    """
    c = ctx(
        playbook_id="playbook_a_pullback",
        trigger_price=95.0, invalidation_price=90.0, current_price=97.5,
        atr=2.0, structural_targets=[105.0],
    )
    result = no_min_participation_engine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.EXCESSIVE_EXTENSION.value in result.reason_codes
    assert result.extension_atr == pytest.approx(1.25, rel=0.05)


def test_pullback_insufficient_rr_rejected():
    """Pullback — only structural target provides R:R=0.6, below minimum 1.5.

    Scenario:
      entry_ref=96.0, inval=90.0 → risk=6.0
      target=99.6 → reward=3.6 → R:R=0.6 < 1.5
      tradeability_state: NOT_TRADEABLE
      reason_code:        INSUFFICIENT_RISK_REWARD
    """
    c = ctx(
        playbook_id="playbook_a_pullback",
        trigger_price=95.0, invalidation_price=90.0, current_price=96.0,
        atr=2.0, structural_targets=[99.6],  # R:R = 3.6/6.0 = 0.6
    )
    result = no_min_participation_engine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.INSUFFICIENT_RISK_REWARD.value in result.reason_codes


# ─── Playbook B: Liquidity Sweep ──────────────────────────────────────────────

def test_sweep_strong_reversal_participation_tradeable():
    """Sweep — strong negative delta on bearish reversal → TRADEABLE.

    Scenario:
      direction:           BEARISH (bearish sweep reversal)
      trigger_price:       95.0 (swept low reclaim — bearish entry on rejection)
      invalidation:        100.0
      current_price:       94.0
      delta:               -90, ESTIMATED_BID_ASK
      rvol:                1.6x (good participation)
      R:R:                 entry=94, inval=100, target=88 → risk=6, reward=6 → 1.0 ... < 2.0
      Actually need min_rr=2.0 for sweep, so adjust target to 82:
        risk=6, reward=12 → R:R=2.0 ≥ 2.0 → TRADEABLE
    """
    baseline = make_baseline(mean=800.0, std=150.0)
    c = ctx(
        playbook_id="playbook_b_liquidity_sweep",
        direction="BEARISH",
        trigger_price=95.0, invalidation_price=100.0, current_price=94.0,
        atr=2.0, current_volume=1280.0, rvol_baseline=baseline,  # 1.6x mean
        delta_value=-90.0, delta_provenance=DeltaProvenance.ESTIMATED_BID_ASK,
        structural_targets=[82.0],  # risk=6, reward=12, R:R=2.0
    )
    result = TradeabilityEngine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.TRADEABLE
    assert result.delta_score > 0
    assert result.risk_reward_to_target1 == pytest.approx(2.0, rel=0.05)


def test_sweep_delta_conflict_reduces_participation():
    """Sweep — positive delta on a bearish sweep trigger = delta conflict.

    Delta score = 0 (no alignment); participation reduced.
    If no other participation source, may fail minimum gate.
    """
    baseline = make_baseline(mean=800.0, std=150.0)
    c = ctx(
        playbook_id="playbook_b_liquidity_sweep",
        direction="BEARISH",
        trigger_price=95.0, invalidation_price=100.0, current_price=94.0,
        atr=2.0, current_volume=1280.0, rvol_baseline=baseline,
        delta_value=70.0, delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,  # positive on bearish = conflict
        structural_targets=[82.0],
    )
    result = TradeabilityEngine().evaluate_tradeability(c)
    # delta_score must be 0 (conflict = no alignment)
    assert result.delta_score == 0.0
    # Note: sweep min_participation=20.0. If RVOL alone is enough → may still be TRADEABLE.
    # The key assertion is delta_score=0, not the final state.


def test_sweep_large_gap_rejected():
    """Sweep — gap_distance_atr=2.0 exceeds max_gap_distance_atr=1.5 for sweep → NOT_TRADEABLE.

    The current_price must be within the extension limit (sweep max_ext=0.75 ATR)
    so the extension gate does not fire before the gap gate.
    trigger=95.0, atr=2.0 → max_ext=0.75×2.0=1.5 pts; current_price=96.0 → ext=0.5 ATR < 0.75 (OK).
    gap_distance_atr=2.0 > sweep max of 1.5 → GAP_TOO_LARGE.
    """
    c = ctx(
        playbook_id="playbook_b_liquidity_sweep",
        direction="BULLISH",
        trigger_price=95.0, invalidation_price=90.0, current_price=96.0,  # ext=0.5 ATR < 0.75
        atr=2.0,
        gap_beyond_trigger=True, gap_distance_atr=2.0,  # 2.0 > sweep limit 1.5
        structural_targets=[105.0],
    )
    result = no_min_participation_engine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.GAP_TOO_LARGE.value in result.reason_codes


def test_sweep_good_structural_rr_tradeable():
    """Sweep — R:R ≥ 2.0 with valid structural target → passes R:R gate."""
    # entry=96, inval=90, target=108 → risk=6, reward=12, R:R=2.0 ≥ 2.0
    c = ctx(
        playbook_id="playbook_b_liquidity_sweep",
        direction="BULLISH",
        trigger_price=95.0, invalidation_price=90.0, current_price=96.0,
        atr=2.0, structural_targets=[108.0],
    )
    result = no_min_participation_engine().evaluate_tradeability(c)
    assert result.risk_reward_to_best_structural_target == pytest.approx(2.0, rel=0.05)
    assert TradeabilityReasonCode.INSUFFICIENT_RISK_REWARD.value not in result.reason_codes


# ─── Playbook C: ORB Breakout ─────────────────────────────────────────────────

def test_orb_high_participation_breakout_tradeable():
    """ORB — strong RVOL + ACTUAL_TRADE_AGGRESSOR delta → TRADEABLE.

    Scenario:
      trigger_price:   105.0 (ORB_HIGH body close)
      current_price:   106.0 (1 bar after trigger)
      rvol:            2.0x mean (strong participation)
      delta:           +90, ACTUAL_TRADE_AGGRESSOR
      extension:       0.5 ATR (within 1.5 ORB limit)
      R:R:             entry=106, inval=95, target=120 → risk=11, reward=14 → 1.27 < 1.5
      Adjust target to 122: reward=16, R:R=1.45 < 1.5 still fails
      Use target=123: reward=17, R:R=1.54 ≥ 1.5 → passes
    """
    baseline = make_baseline(mean=1200.0, std=250.0)
    c = ctx(
        playbook_id="playbook_c_orb_breakout",
        trigger_price=105.0, invalidation_price=95.0, current_price=106.0,
        atr=2.0, current_volume=2400.0, rvol_baseline=baseline,  # 2.0x mean
        delta_value=90.0, delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        structural_targets=[123.0],  # R:R = 17/11 = 1.54 ≥ 1.5
    )
    result = TradeabilityEngine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.TRADEABLE
    assert result.rvol_normalized == pytest.approx(2.0, rel=0.05)
    assert result.delta_score > 0
    assert result.risk_reward_to_target1 > 1.5


def test_orb_low_participation_rejected():
    """ORB — RVOL=0.4x mean, no delta → participation below ORB minimum (35.0).

    ORB requires higher participation than pullback (35.0 vs 25.0).
    """
    baseline = make_baseline(mean=1200.0, std=250.0)
    c = ctx(
        playbook_id="playbook_c_orb_breakout",
        trigger_price=105.0, invalidation_price=95.0, current_price=106.0,
        atr=2.0, current_volume=480.0, rvol_baseline=baseline,  # 0.4x mean — low
        delta_value=None, delta_provenance=DeltaProvenance.UNAVAILABLE,
        structural_targets=[123.0],
    )
    result = TradeabilityEngine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.INSUFFICIENT_PARTICIPATION.value in result.reason_codes


def test_orb_breakout_too_extended_rejected():
    """ORB — price chased 1.6 ATR above trigger → EXCESSIVE_EXTENSION.

    ORB max_extension_atr=1.5.
    trigger=105.0, atr=2.0 → max_ext=3.0 pts; current_price=108.3 → 1.65 ATR > 1.5.
    """
    c = ctx(
        playbook_id="playbook_c_orb_breakout",
        trigger_price=105.0, invalidation_price=95.0, current_price=108.3,
        atr=2.0, structural_targets=[123.0],
    )
    result = no_min_participation_engine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.EXCESSIVE_EXTENSION.value in result.reason_codes
    assert result.extension_atr == pytest.approx(1.65, rel=0.05)


def test_orb_spread_too_wide_rejected():
    """ORB — bid/ask spread > max_pct (0.05%) → SPREAD_TOO_WIDE → NOT_TRADEABLE.

    max_pct=0.05 means 5% of price. To exceed it:
    current_price=106.0; for 5% of 106 = 5.30 pts of spread.
    bid=103.0, ask=109.0 → spread=6.0 / 106.0 = 5.66% > 5%.
    """
    c = ctx(
        playbook_id="playbook_c_orb_breakout",
        trigger_price=105.0, invalidation_price=95.0, current_price=106.0,
        atr=2.0, structural_targets=[123.0],
        bid=103.0, ask=109.0,  # 6.0 pts spread / 106 = 5.66% > max_pct=5%
    )
    result = no_min_participation_engine().evaluate_tradeability(c)
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.SPREAD_TOO_WIDE.value in result.reason_codes
    assert result.liquidity_status == "WIDE"
