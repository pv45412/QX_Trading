import pytest
from qx.tradeability.engine import TradeabilityEngine, _compute_extension, _compute_rr
from qx.tradeability.models import (
    TradeabilityMarketEvidence,
    TradeabilityContext,
    TradeabilityState,
    TradeabilityReasonCode,
    RVOLBaseline,
    LiquidityApplicability,
)
from qx.models.rules import SignalState, PublicationState, DeltaProvenance
from qx.triggers.models import TriggeredSetupResult, TriggerEvent
from qx.config.rules_config import load_rules_config, TargetSelectionPolicy
from qx.tradeability.rvol import compute_rvol, _validate_baseline_identity

def _dummy_evidence(price=100.0, target=105.0) -> TradeabilityMarketEvidence:
    return TradeabilityMarketEvidence(
        current_price=price,
        atr=2.0,
        evaluation_timestamp="2026-09-15T10:05:00Z",
        data_as_of="2026-09-15T10:05:00Z",
        structural_target_candidates=[target],
        liquidity_applicability=LiquidityApplicability.NOT_APPLICABLE,
    )

def _dummy_setup(direction="BULLISH", trigger=99.0, invalidation=95.0) -> TriggeredSetupResult:
    return TriggeredSetupResult(
        playbook_evaluation_id="pb_eval_1",
        playbook_id="playbook_a_pullback",
        symbol="AAPL",
        timeframe="5m",
        direction=direction,
        state=SignalState.TRIGGERED,
        trigger_price=trigger,
        invalidation_price=invalidation,
        trigger_event_timestamp="2026-09-15T10:00:00Z",
        armed_at="2026-09-15T09:55:00Z",
        trigger_level_known_at="2026-09-15T09:50:00Z",
        trigger_confirmed_at="2026-09-15T10:05:00Z",
        publication_state=PublicationState.VERIFIED,
        trigger_event=TriggerEvent(
            trigger_event_id="te_1",
            playbook_id="playbook_a_pullback",
            symbol="AAPL",
            trigger_source_type="TEST",
            trigger_source_id="ts_1",
            trigger_rule_type="CLOSE_ABOVE_LEVEL",
            event_timestamp="2026-09-15T10:00:00Z",
            knowledge_timestamp="2026-09-15T10:00:00Z",
            confirmed_at="2026-09-15T10:05:00Z",
            observed_price=trigger,
            bar_open=trigger,
            bar_high=trigger,
            bar_low=trigger,
            bar_close=trigger,
            source_playbook_evaluation_id="pb_eval_1",
            trigger_price=trigger,
            gap_beyond_trigger=False,
            gap_distance_atr=0.0
        )
    )

def test_participation_score_calculated_before_participation_gate():
    cfg = load_rules_config()
    cfg.tradeability.min_participation["playbook_a_pullback"] = 99.0
    engine = TradeabilityEngine(cfg)
    
    evidence = _dummy_evidence(price=100.0, target=110.0)
    evidence.delta_provenance = DeltaProvenance.ACTUAL_TRADE_AGGRESSOR
    evidence.delta_value = 50.0 # High alignment but score will be ~50 < 99
    
    setup = _dummy_setup()
    result = engine.evaluate_triggered_setup(setup, evidence)
    
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.INSUFFICIENT_PARTICIPATION.value in result.reason_codes
    assert result.participation_score > 0.0 # Was calculated before gate
    
def test_high_participation_cannot_override_failed_rr_gate():
    cfg = load_rules_config()
    cfg.tradeability.min_risk_reward["playbook_a_pullback"] = 5.0 # Very high RR required
    engine = TradeabilityEngine(cfg)
    
    evidence = _dummy_evidence(price=100.0, target=102.0) # Only 2.0 / 5.0 = 0.4 RR
    evidence.delta_provenance = DeltaProvenance.ACTUAL_TRADE_AGGRESSOR
    evidence.delta_value = 100.0 # High alignment
    
    setup = _dummy_setup()
    result = engine.evaluate_triggered_setup(setup, evidence)
    
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.INSUFFICIENT_RISK_REWARD.value in result.reason_codes

def test_high_participation_cannot_override_extension_gate():
    cfg = load_rules_config()
    cfg.tradeability.max_extension_atr["playbook_a_pullback"] = 0.1
    engine = TradeabilityEngine(cfg)
    
    evidence = _dummy_evidence(price=105.0) # Extended far beyond trigger 99.0
    evidence.delta_provenance = DeltaProvenance.ACTUAL_TRADE_AGGRESSOR
    evidence.delta_value = 100.0
    
    setup = _dummy_setup()
    result = engine.evaluate_triggered_setup(setup, evidence)
    
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.EXCESSIVE_EXTENSION.value in result.reason_codes

def test_bullish_extension_is_directional():
    ext = _compute_extension(current_price=105.0, trigger_price=100.0, atr=2.0, direction="BULLISH")
    assert ext == 2.5 # (105-100) / 2

def test_bearish_extension_is_directional():
    ext = _compute_extension(current_price=95.0, trigger_price=100.0, atr=2.0, direction="BEARISH")
    assert ext == 2.5 # (100-95) / 2

def test_adverse_move_is_not_counted_as_favorable_extension():
    ext = _compute_extension(current_price=95.0, trigger_price=100.0, atr=2.0, direction="BULLISH")
    assert ext == 0.0 # Adverse move

def test_zero_risk_geometry_rejected():
    gate, best = _compute_rr(current_price=100.0, invalidation_price=100.0, targets=[105.0], direction="BULLISH")
    assert gate is None
    
def test_negative_risk_geometry_rejected():
    gate, best = _compute_rr(current_price=100.0, invalidation_price=105.0, targets=[110.0], direction="BULLISH")
    assert gate is None

def test_target_on_wrong_side_of_entry_rejected():
    gate, best = _compute_rr(current_price=100.0, invalidation_price=95.0, targets=[90.0], direction="BULLISH")
    assert gate is None
    
def test_invalidation_on_wrong_side_of_entry_rejected():
    gate, best = _compute_rr(current_price=100.0, invalidation_price=95.0, targets=[90.0], direction="BEARISH")
    assert gate is None

def test_rr_gate_uses_configured_target_policy():
    # T1 = nearest (101.0, RR=1/5=0.2)
    # T2 = distant (120.0, RR=20/5=4.0)
    # NEAREST_VALID_TARGET policy should return 0.2
    gate, best = _compute_rr(
        current_price=100.0, invalidation_price=95.0, 
        targets=[101.0, 120.0], direction="BULLISH", 
        target_policy="NEAREST_VALID_TARGET"
    )
    assert gate == 0.2
    assert best == 4.0

def test_distant_target_cannot_hide_poor_nearest_target_rr():
    cfg = load_rules_config()
    cfg.tradeability.min_risk_reward["playbook_a_pullback"] = 1.5
    cfg.tradeability.risk_reward.gate_target_policy = TargetSelectionPolicy.NEAREST_VALID_TARGET
    engine = TradeabilityEngine(cfg)
    
    evidence = _dummy_evidence(price=100.0)
    evidence.structural_target_candidates = [101.0, 120.0]
    
    setup = _dummy_setup() # trigger 99, inv 95, risk = 5.
    result = engine.evaluate_triggered_setup(setup, evidence)
    
    assert result.state == TradeabilityState.NOT_TRADEABLE
    assert TradeabilityReasonCode.INSUFFICIENT_RISK_REWARD.value in result.reason_codes

def test_rvol_same_slot_respects_market_timezone():
    baseline = RVOLBaseline(
        symbol="AAPL", timeframe="5m", time_slot="09:35", 
        slot_mean_volume=1000, slot_median_volume=1000, slot_std=100, 
        baseline_sessions_used=20, baseline_computed_at="now",
        slot_timezone="America/New_York"
    )
    with pytest.raises(ValueError, match="timezone does not match"):
        _validate_baseline_identity(
            baseline, expected_symbol="AAPL", expected_timeframe="5m", 
            expected_time_slot="09:35", expected_timezone="Europe/London"
        )

def test_rvol_does_not_mix_rth_and_eth_slots():
    baseline = RVOLBaseline(
        symbol="AAPL", timeframe="5m", time_slot="09:35", 
        slot_mean_volume=1000, slot_median_volume=1000, slot_std=100, 
        baseline_sessions_used=20, baseline_computed_at="now",
        session_type="RTH"
    )
    with pytest.raises(ValueError, match="session type does not match"):
        _validate_baseline_identity(
            baseline, expected_symbol="AAPL", expected_timeframe="5m", 
            expected_time_slot="09:35", expected_session_type="ETH"
        )

def test_rvol_baseline_excludes_current_session():
    baseline = RVOLBaseline(
        symbol="AAPL", timeframe="5m", time_slot="09:35", 
        slot_mean_volume=1000, slot_median_volume=1000, slot_std=100, 
        baseline_sessions_used=20, baseline_computed_at="now",
        baseline_session_dates=["2026-09-14", "2026-09-15"]
    )
    with pytest.raises(ValueError, match="leaked current evaluation session data"):
        _validate_baseline_identity(
            baseline, expected_symbol="AAPL", expected_timeframe="5m", 
            expected_time_slot="09:35", evaluation_session_date="2026-09-15"
        )

def test_liquidity_not_applicable_passes():
    cfg = load_rules_config()
    engine = TradeabilityEngine(cfg)
    
    evidence = _dummy_evidence()
    evidence.liquidity_applicability = LiquidityApplicability.NOT_APPLICABLE
    evidence.bid = None
    evidence.ask = None
    
    setup = _dummy_setup()
    result = engine.evaluate_triggered_setup(setup, evidence)
    
    assert TradeabilityReasonCode.SPREAD_TOO_WIDE.value not in result.reason_codes
    assert TradeabilityReasonCode.LIQUIDITY_UNKNOWN.value not in result.reason_codes
    assert result.liquidity_status == "NOT_APPLICABLE"

def test_bullish_sweep_positive_delta_supports_participation():
    cfg = load_rules_config()
    engine = TradeabilityEngine(cfg)
    evidence = _dummy_evidence(price=100.0, target=110.0)
    evidence.delta_provenance = DeltaProvenance.ACTUAL_TRADE_AGGRESSOR
    evidence.delta_value = 50.0 # Positive delta
    setup = _dummy_setup(direction="BULLISH")
    
    result = engine.evaluate_triggered_setup(setup, evidence)
    assert result.delta_score > 0.0

def test_bearish_sweep_negative_delta_supports_participation():
    cfg = load_rules_config()
    engine = TradeabilityEngine(cfg)
    evidence = _dummy_evidence(price=100.0, target=90.0)
    evidence.delta_provenance = DeltaProvenance.ACTUAL_TRADE_AGGRESSOR
    evidence.delta_value = -50.0 # Negative delta
    setup = _dummy_setup(direction="BEARISH", trigger=101.0, invalidation=105.0)
    
    result = engine.evaluate_triggered_setup(setup, evidence)
    assert result.delta_score > 0.0
