"""Phase 1: Unit tests for Data Models, Enums, and Configuration Versioning."""

from qx.config.rules_config import load_rules_config
from qx.models.rules import (
    CalibrationStatus,
    DeltaProvenance,
    DeterministicSignalResult,
    GammaRegime,
    MarketRegimeModel,
    PublicationState,
    RuleResult,
    RuleSeverity,
    SessionRegime,
    SignalState,
    TrendRegime,
    VolatilityRegime,
)


def test_signal_state_and_publication_state_are_independent():
    """Verify PublicationState and SignalState use separate enums and can vary independently."""
    # A research-only signal can be ARMED
    pub_state = PublicationState.SIMULATED
    sig_state = SignalState.ARMED
    assert pub_state != sig_state
    assert pub_state.value == "SIMULATED"
    assert sig_state.value == "ARMED"

    # A verified data signal can be BLOCKED
    pub_state_2 = PublicationState.VERIFIED
    sig_state_2 = SignalState.BLOCKED
    assert pub_state_2.value == "VERIFIED"
    assert sig_state_2.value == "BLOCKED"


import pytest


def test_execution_requires_verified_publication_state():
    """Execution eligibility requires publication_state == VERIFIED and signal_state == EXECUTABLE."""
    regime = MarketRegimeModel(
        trend=TrendRegime.TREND_UP,
        volatility=VolatilityRegime.NORMAL,
        gamma=GammaRegime.POSITIVE_GAMMA,
        session=SessionRegime.TREND_SESSION,
    )

    # Simulated publication state with EXECUTABLE signal state -> Hard invariant raises ValueError
    with pytest.raises((ValueError, Exception), match="Hard invariant violation: signal_state cannot be EXECUTABLE"):
        DeterministicSignalResult(
            signal_id="SIG-001",
            symbol="XLK",
            publication_state=PublicationState.SIMULATED,
            data_as_of="2026-09-15 16:00 UTC",
            generated_at="2026-09-15 16:00:01 UTC",
            market_regime=regime,
            direction="BULLISH",
            direction_score=75.0,
            playbook_id="PLAYBOOK_A_PULLBACK",
            setup_quality=85.0,
            participation_score=80.0,
            market_alignment_score=90.0,
            tradeability_score=88.0,
            signal_state=SignalState.EXECUTABLE,
        )

    # Verified publication state + EXECUTABLE signal state -> Allowed
    ver_res = DeterministicSignalResult(
        signal_id="SIG-001",
        symbol="XLK",
        publication_state=PublicationState.VERIFIED,
        data_as_of="2026-09-15 16:00 UTC",
        generated_at="2026-09-15 16:00:01 UTC",
        market_regime=regime,
        direction="BULLISH",
        direction_score=75.0,
        playbook_id="PLAYBOOK_A_PULLBACK",
        setup_quality=85.0,
        participation_score=80.0,
        market_alignment_score=90.0,
        tradeability_score=88.0,
        signal_state=SignalState.EXECUTABLE,
    )
    assert ver_res.publication_state == PublicationState.VERIFIED
    assert ver_res.signal_state == SignalState.EXECUTABLE


def test_blocked_state_requires_new_evaluation_cycle():
    """BLOCKED is an absorbing result; a blocked evaluation cycle cannot become EXECUTABLE without re-evaluation."""
    sig_result = DeterministicSignalResult(
        signal_id="SIG-002",
        symbol="XLK",
        publication_state=PublicationState.BLOCKED,
        data_as_of="Stale Timestamp",
        generated_at="2026-09-15 16:00:01 UTC",
        market_regime=MarketRegimeModel(
            trend=TrendRegime.RANGE,
            volatility=VolatilityRegime.COMPRESSED,
            gamma=GammaRegime.UNKNOWN,
            session=SessionRegime.OPENING,
        ),
        direction="NEUTRAL",
        direction_score=0.0,
        playbook_id="NONE",
        setup_quality=0.0,
        participation_score=0.0,
        market_alignment_score=0.0,
        tradeability_score=0.0,
        signal_state=SignalState.BLOCKED,
    )

    # In a blocked state, the signal state must be BLOCKED
    assert sig_result.signal_state == SignalState.BLOCKED
    assert sig_result.publication_state == PublicationState.BLOCKED


def test_order_block_requires_structural_consequence():
    """Order block configuration requires candidate opposite candle + minimum displacement + structural consequence (BOS/CHoCH)."""
    cfg = load_rules_config()
    ob_cfg = cfg.order_block_validation
    assert ob_cfg.min_displacement_atr == 1.00
    assert ob_cfg.min_body_multiplier == 1.50
    assert ob_cfg.require_structural_consequence is True


def test_liquidity_sweep_supports_bullish_and_bearish_reversal_logic():
    """Playbook B configuration supports directional rules for both bullish and bearish sweeps."""
    cfg = load_rules_config()
    pb_b = cfg.playbooks.get("playbook_b_liquidity_sweep", {})
    dir_rules = pb_b.get("directional_rules", {})

    assert "bullish_sweep" in dir_rules
    assert "bearish_sweep" in dir_rules
    assert dir_rules["bullish_sweep"]["require_low_sweep"] is True
    assert dir_rules["bearish_sweep"]["require_high_sweep"] is True


def test_rule_result_severity():
    """Verify RuleResult exposes RuleSeverity (INFO, SOFT, HARD) and data provenance."""
    rule = RuleResult(
        rule_id="QX-GATE-001",
        category="DATA_GATE",
        required_value="VERIFIED",
        observed_value="SIMULATED",
        passed=False,
        severity=RuleSeverity.HARD,
        hard_gate=True,
        data_source=DeltaProvenance.BAR_DERIVED,
        detail="Data source is simulated; hard gate veto applied.",
    )
    assert rule.severity == RuleSeverity.HARD
    assert rule.hard_gate is True
    assert rule.data_source == DeltaProvenance.BAR_DERIVED
