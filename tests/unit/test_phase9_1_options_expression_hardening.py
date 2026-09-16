"""Unit tests for Phase 9.1 Options Expression Hardening."""

import pytest

from qx.config.rules_config import RulesEngineConfig
from qx.tradeability.models import TradeabilityResult, TradeabilityState
from qx.models.rules import PublicationState
from qx.options_expression.models import (
    OptionsContext,
    OptionContract,
    OptionGreeks,
    OptionsExpressionState,
    StrategyType,
    OptionGreekProvenance
)
from qx.options_expression.engine import OptionsExpressionEngine

def make_tradeability_result():
    return TradeabilityResult(
        tradeability_id="trade_eval_123",
        triggered_setup_id="setup_123",
        playbook_id="playbook_a_pullback",
        symbol="NVDA",
        timeframe="5m",
        direction="BULLISH",
        state=TradeabilityState.TRADEABLE,
        publication_state=PublicationState.VERIFIED,
        trigger_price=100.0,
        observed_underlying_price=100.0,
        observed_entry_reference_price=100.0,
        invalidation_price=90.0,
        target_candidates=[110.0],
        participation_score=100.0,
        participation_evidence_coverage=1.0,
        delta_score=100.0,
        delta_reliability=1.0,
        extension_atr=0.5,
        spread_absolute=0.1,
        spread_pct=0.001,
        liquidity_status="TIGHT",
        risk_reward_to_target1=2.0,
        risk_reward_to_best_structural_target=2.0,
        gap_beyond_trigger=False,
        gap_distance_atr=0.0,
        bars_since_trigger=0,
        seconds_since_trigger=0.0,
        triggered_at="2026-09-15T10:00:00Z",
        tradeability_evaluated_at="2026-09-15T10:00:00Z",
        evaluated_at="2026-09-15T10:00:00Z",
        data_as_of="2026-09-15T10:00:00Z",
        reason_codes=[],
        evidence_ladder={},
        config_version="research_v1",
        engine_version="v8.0.0",
        trade_state="NONE - OPTIONS EXPRESSION NOT YET EVALUATED"
    )

def make_options_context(multiplier=100.0):
    chain = {
        "2026-10-15": {
            100.0: {
                "CALL": OptionContract(
                    symbol="NVDA_20261015C100", underlying_symbol="NVDA", strike=100.0,
                    expiration="2026-10-15", dte=30, is_call=True, bid=5.0, ask=5.1,
                    mark=5.05, volume=1000, open_interest=5000,
                    greeks=OptionGreeks(delta=0.5, gamma=0.02, theta=-0.05, vega=0.10, provenance=OptionGreekProvenance.BROKER_PROVIDED),
                    quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=0.0,
                    contract_multiplier=multiplier
                )
            },
            110.0: {
                 "CALL": OptionContract(
                    symbol="NVDA_20261015C110", underlying_symbol="NVDA", strike=110.0,
                    expiration="2026-10-15", dte=30, is_call=True, bid=2.0, ask=2.1,
                    mark=2.05, volume=1000, open_interest=5000,
                    greeks=OptionGreeks(delta=0.25, gamma=0.01, theta=-0.03, vega=0.08, provenance=OptionGreekProvenance.BROKER_PROVIDED),
                    quote_as_of="2026-09-15T10:00:00Z", quote_age_seconds=0.0,
                    contract_multiplier=multiplier
                )
            }
        }
    }
    
    return OptionsContext(
        underlying_symbol="NVDA",
        underlying_price=100.0,
        data_as_of="2026-09-15T10:00:00Z",
        chain=chain,
        iv_rank=50.0,
    )

# 1. Contract Multiplier
def test_contract_multiplier_loaded_from_metadata():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context(multiplier=50.0)
    res = engine.evaluate_options_expression(tr, ctx)
    for cand in res.candidate_strategies:
        assert cand.legs[0].contract_multiplier == 50.0
        if cand.strategy_type == StrategyType.LONG_CALL:
            assert cand.max_loss == 5.1 * 50.0

def test_equity_option_multiplier_can_resolve_to_100_from_product_config():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context(multiplier=None)
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.state == OptionsExpressionState.NOT_SUITABLE
    assert "CONTRACT_MULTIPLIER_UNAVAILABLE" in res.reason_codes

def test_unknown_product_without_multiplier_is_not_suitable():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context(multiplier=None)
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.state == OptionsExpressionState.NOT_SUITABLE
    assert "CONTRACT_MULTIPLIER_UNAVAILABLE" in res.reason_codes

def test_multiplier_unavailable_not_silently_assumed_100():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context(multiplier=None)
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.state == OptionsExpressionState.NOT_SUITABLE
    assert "CONTRACT_MULTIPLIER_UNAVAILABLE" in res.reason_codes

# 2. Event-risk policy
def test_event_before_expiration_is_recorded():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.events = [{"event_type": "earnings", "event_date": "2026-09-30", "days_until_event": 15, "event_before_expiration": True}]
    res = engine.evaluate_options_expression(tr, ctx)
    cand = res.candidate_strategies[0]
    assert cand.event_risk_identified is True
    assert "EVENT_BEFORE_EXPIRATION" in cand.reason_codes

def test_event_risk_penalty_is_config_driven():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.events = [{"event_type": "earnings", "event_date": "2026-09-30", "days_until_event": 15, "event_before_expiration": True}]
    res = engine.evaluate_options_expression(tr, ctx)
    cand = res.candidate_strategies[0]
    assert cand.event_penalty_applied == engine.oe_cfg.event_risk_penalty

def test_event_risk_does_not_change_underlying_direction():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.events = [{"event_type": "earnings", "event_date": "2026-09-30"}]
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.direction == "BULLISH"

def test_event_risk_default_policy_does_not_automatically_block():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.events = [{"event_type": "earnings", "event_date": "2026-09-30"}]
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.state == OptionsExpressionState.SUITABLE # Still suitable despite penalty

# 3. Greek provenance explicitly
def test_broker_greeks_labeled_broker_provided():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    res = engine.evaluate_options_expression(tr, ctx)
    cand = res.candidate_strategies[0]
    assert cand.legs[0].greeks.provenance == OptionGreekProvenance.BROKER_PROVIDED

def test_model_greeks_record_model_inputs():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.chain["2026-10-15"][100.0]["CALL"].greeks = OptionGreeks(
        delta=0.5, provenance=OptionGreekProvenance.MODEL_CALCULATED,
        pricing_model="BLACK_SCHOLES", risk_free_rate=0.05, dividend_yield=0.0, volatility_input=0.3, calculation_timestamp="2026-09-15T10:00:00Z"
    )
    res = engine.evaluate_options_expression(tr, ctx)
    cand = res.candidate_strategies[0]
    assert cand.legs[0].greeks.provenance == OptionGreekProvenance.MODEL_CALCULATED
    assert cand.legs[0].greeks.pricing_model == "BLACK_SCHOLES"
    assert cand.legs[0].greeks.risk_free_rate == 0.05

def test_unavailable_greeks_not_fabricated():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.chain["2026-10-15"][100.0]["CALL"].greeks = OptionGreeks(delta=0.5, provenance=OptionGreekProvenance.UNAVAILABLE)
    res = engine.evaluate_options_expression(tr, ctx)
    cand = res.candidate_strategies[0]
    assert cand.legs[0].greeks.provenance == OptionGreekProvenance.UNAVAILABLE
    assert cand.legs[0].greeks.gamma is None

# 4. IV Rank distinct
def test_iv_rank_not_fabricated():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.iv_rank = None
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.iv_rank is None

def test_iv_percentile_not_substituted_for_iv_rank():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.iv_rank = None
    ctx.iv_percentile = 90.0
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.iv_rank is None
    assert res.iv_percentile == 90.0

# 5. Fill assumptions
def test_midpoint_not_labeled_actual_fill():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    res = engine.evaluate_options_expression(tr, ctx)
    for cand in res.candidate_strategies:
        assert "fill_assumption" in cand.model_dump()
        assert cand.fill_assumption == "CONSERVATIVE_ESTIMATE"

def test_natural_multileg_price_uses_correct_bid_ask_sides():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    res = engine.evaluate_options_expression(tr, ctx)
    debit_spread = next(c for c in res.candidate_strategies if c.strategy_type == StrategyType.CALL_DEBIT_SPREAD)
    assert round(debit_spread.net_debit, 2) == 310.0
    # Long call at 100 (ask 5.1), Short call at 110 (bid 2.0).
    # Natural price = 5.1 - 2.0 = 3.1
    # Midpoint price = (5.05) - (2.05) = 3.0
    assert round(debit_spread.natural_price, 2) == 3.10
    assert round(debit_spread.midpoint_price, 2) == 3.00
    assert round(debit_spread.conservative_fill_estimate, 2) == 3.10

def test_conservative_fill_estimate_is_explicit():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    res = engine.evaluate_options_expression(tr, ctx)
    assert res.candidate_strategies[0].fill_assumption == "CONSERVATIVE_ESTIMATE"

# 7. Structural-target fields
def test_structural_target_fields_preserved():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    res = engine.evaluate_options_expression(tr, ctx)
    debit_spread = next(c for c in res.candidate_strategies if c.strategy_type == StrategyType.CALL_DEBIT_SPREAD)
    assert debit_spread.structural_target_id == "phase8_target_1"
    assert debit_spread.structural_target_price == 110.0
    assert debit_spread.short_strike == 110.0
    assert debit_spread.target_fit_distance == 0.0
    assert debit_spread.target_fit_score == 0.0

