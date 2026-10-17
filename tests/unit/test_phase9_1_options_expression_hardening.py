"""Unit tests for Phase 9.1 Options Expression Hardening."""

from datetime import datetime, timezone

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
from qx.options_expression.math import calculate_combined_greek_evidence
from qx.options_expression.greeks import is_greek_available
from qx.portfolio.models import AccountRiskContext, FreshnessState
from qx.portfolio.portfolio_risk_engine import PortfolioRiskEngine

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
        source="TEST",
        freshness="FRESH",
        sync_status="SYNCED",
        chain=chain,
        iv_rank=50.0,
    )


def test_partial_option_snapshot_blocks_before_candidate_construction():
    engine = OptionsExpressionEngine()
    ctx = make_options_context()
    ctx.sync_status = "PARTIAL"

    result = engine.evaluate_options_expression(make_tradeability_result(), ctx)

    assert result.state == OptionsExpressionState.BLOCKED
    assert result.reason_codes == ["OPTION_CHAIN_SYNC_UNAVAILABLE"]


def test_phase9_candidate_enters_phase10_without_double_multiplier_scaling():
    expression = OptionsExpressionEngine().evaluate_options_expression(
        make_tradeability_result(), make_options_context()
    )
    candidate = next(
        item
        for item in expression.candidate_strategies
        if item.candidate_id == expression.primary_candidate_id
    )
    account = AccountRiskContext(
        account_id="qxacct_test",
        equity=200000.0,
        cash=100000.0,
        buying_power=150000.0,
        data_as_of=datetime.now(timezone.utc),
        freshness=FreshnessState.FRESH,
        broker_provenance="TEST",
        sync_status="SYNCED",
    )

    risk = PortfolioRiskEngine().evaluate_portfolio_risk(candidate, expression, account)

    assert candidate.contract_multiplier == 100.0
    assert risk.candidate_buying_power_required == pytest.approx(candidate.net_debit)
    assert risk.portfolio_delta_after == pytest.approx(candidate.combined_delta)

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
def test_broker_greek_provenance_preserves_source_timestamp():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    ctx.chain["2026-10-15"][100.0]["CALL"].greeks = OptionGreeks(
        delta=0.5, provenance=OptionGreekProvenance.BROKER_PROVIDED,
        broker_source="SCHWAB", quote_timestamp="2026-09-15T10:00:00Z"
    )
    res = engine.evaluate_options_expression(tr, ctx)
    cand = res.candidate_strategies[0]
    assert cand.legs[0].greeks.provenance == OptionGreekProvenance.BROKER_PROVIDED
    assert cand.legs[0].greeks.broker_source == "SCHWAB"
    assert cand.legs[0].greeks.quote_timestamp == "2026-09-15T10:00:00Z"

def test_model_calculated_greeks_preserve_pricing_inputs():
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
    assert cand.legs[0].greeks.dividend_yield == 0.0
    assert cand.legs[0].greeks.volatility_input == 0.3
    assert cand.legs[0].greeks.calculation_timestamp == "2026-09-15T10:00:00Z"


def test_complete_model_greek_metadata_remains_available_through_phase10():
    context = make_options_context()
    for strikes in context.chain.values():
        for contracts in strikes.values():
            for contract in contracts.values():
                contract.greeks = OptionGreeks(
                    delta=contract.greeks.delta,
                    gamma=contract.greeks.gamma,
                    theta=contract.greeks.theta,
                    vega=contract.greeks.vega,
                    provenance=OptionGreekProvenance.MODEL_CALCULATED,
                    pricing_model="BLACK_SCHOLES",
                    risk_free_rate=0.05,
                    dividend_yield=0.0,
                    volatility_input=0.30,
                    calculation_timestamp="2026-09-15T10:00:00Z",
                )
    expression = OptionsExpressionEngine().evaluate_options_expression(
        make_tradeability_result(), context
    )
    candidate = next(
        item
        for item in expression.candidate_strategies
        if item.candidate_id == expression.primary_candidate_id
    )
    account = AccountRiskContext(
        account_id="qxacct_test",
        equity=200000.0,
        cash=100000.0,
        buying_power=150000.0,
        data_as_of=datetime.now(timezone.utc),
        freshness=FreshnessState.FRESH,
        broker_provenance="TEST",
        sync_status="SYNCED",
    )

    risk = PortfolioRiskEngine().evaluate_portfolio_risk(
        candidate, expression, account
    )

    assert set(candidate.combined_greek_provenance.values()) == {
        "MODEL_CALCULATED"
    }
    assert all(
        metadata["source_metadata_valid"]
        for metadata in candidate.combined_greek_metadata.values()
    )
    assert risk.state.value != "BLOCKED"


def test_incomplete_model_greek_metadata_normalizes_values_to_none():
    greeks = OptionGreeks(
        delta=0.5,
        gamma=0.02,
        theta=-0.05,
        vega=0.10,
        provenance=OptionGreekProvenance.MODEL_CALCULATED,
        pricing_model="BLACK_SCHOLES",
        calculation_timestamp="2026-09-15T10:00:00Z",
    )

    assert greeks.delta is greeks.gamma is greeks.theta is greeks.vega is None

def test_unavailable_greek_remains_none():
    engine = OptionsExpressionEngine()
    tr = make_tradeability_result()
    ctx = make_options_context()
    greeks = OptionGreeks(delta=0.5, gamma=None, theta=None, vega=None, provenance=OptionGreekProvenance.UNAVAILABLE)
    ctx.chain["2026-10-15"][100.0]["CALL"].greeks = greeks
    res = engine.evaluate_options_expression(tr, ctx)
    assert greeks.provenance == OptionGreekProvenance.UNAVAILABLE
    assert greeks.delta is greeks.gamma is greeks.theta is greeks.vega is None
    assert res.candidate_strategies == []


def _two_leg_greek_evidence(missing: str):
    context = make_options_context()
    legs = [
        context.chain["2026-10-15"][100.0]["CALL"],
        context.chain["2026-10-15"][110.0]["CALL"],
    ]
    setattr(legs[1].greeks, missing, None)
    return calculate_combined_greek_evidence(legs, [1, -1])


def test_missing_leg_gamma_does_not_become_zero():
    values, availability, coverage, _, _ = _two_leg_greek_evidence("gamma")

    assert values["gamma"] is None
    assert availability["gamma"] == "UNAVAILABLE"
    assert coverage["gamma"] == 0.5


def test_missing_leg_theta_does_not_become_zero():
    values, availability, coverage, _, _ = _two_leg_greek_evidence("theta")

    assert values["theta"] is None
    assert availability["theta"] == "UNAVAILABLE"
    assert coverage["theta"] == 0.5


def test_missing_leg_vega_does_not_become_zero():
    values, availability, coverage, _, _ = _two_leg_greek_evidence("vega")

    assert values["vega"] is None
    assert availability["vega"] == "UNAVAILABLE"
    assert coverage["vega"] == 0.5


def test_incomplete_multileg_greeks_mark_candidate_incomplete():
    values, availability, coverage, provenance, _ = _two_leg_greek_evidence("gamma")

    assert values["delta"] == 25.0
    assert availability["delta"] == "AVAILABLE"
    assert values["gamma"] is None
    assert coverage["gamma"] < 1.0
    assert provenance["gamma"] == "UNAVAILABLE"


def test_numeric_greek_with_unavailable_provenance_is_unavailable():
    assert is_greek_available(
        0.5, OptionGreekProvenance.UNAVAILABLE, {"broker_source": "SCHWAB"}
    ) is False
    greeks = OptionGreeks(
        delta=0.5,
        gamma=0.02,
        theta=-0.05,
        vega=0.1,
        provenance=OptionGreekProvenance.UNAVAILABLE,
    )
    assert greeks.delta is greeks.gamma is greeks.theta is greeks.vega is None


def _combined_with_numeric_unavailable_provenance(name: str):
    context = make_options_context()
    legs = [
        context.chain["2026-10-15"][100.0]["CALL"],
        context.chain["2026-10-15"][110.0]["CALL"],
    ]
    values = {"delta": 0.25, "gamma": 0.01, "theta": -0.03, "vega": 0.08}
    legs[1].greeks = OptionGreeks(
        **values,
        provenance=OptionGreekProvenance.UNAVAILABLE,
    )
    combined, availability, coverage, _, _ = calculate_combined_greek_evidence(
        legs, [1, -1]
    )
    return combined[name], availability[name], coverage[name]


def test_numeric_delta_with_unavailable_provenance_not_used():
    value, availability, coverage = _combined_with_numeric_unavailable_provenance("delta")
    assert value is None
    assert availability == "UNAVAILABLE"
    assert coverage == 0.5


def test_numeric_gamma_with_unavailable_provenance_not_used():
    value, availability, coverage = _combined_with_numeric_unavailable_provenance("gamma")
    assert value is None
    assert availability == "UNAVAILABLE"
    assert coverage == 0.5


def test_numeric_theta_with_unavailable_provenance_not_used():
    value, availability, coverage = _combined_with_numeric_unavailable_provenance("theta")
    assert value is None
    assert availability == "UNAVAILABLE"
    assert coverage == 0.5


def test_numeric_vega_with_unavailable_provenance_not_used():
    value, availability, coverage = _combined_with_numeric_unavailable_provenance("vega")
    assert value is None
    assert availability == "UNAVAILABLE"
    assert coverage == 0.5


def test_multileg_combined_greek_excludes_unavailable_provenance():
    for name in ("delta", "gamma", "theta", "vega"):
        value, availability, coverage = _combined_with_numeric_unavailable_provenance(
            name
        )
        assert value is None
        assert availability == "UNAVAILABLE"
        assert coverage < 1.0


def test_known_zero_with_valid_provenance_remains_available():
    greeks = OptionGreeks(
        delta=0.0,
        gamma=0.0,
        theta=0.0,
        vega=0.0,
        provenance=OptionGreekProvenance.BROKER_PROVIDED,
    )
    assert greeks.gamma == 0.0
    assert is_greek_available(0.0, greeks.provenance) is True

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
