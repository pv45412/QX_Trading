"""Phase 5 Characterization Scenarios.

Exhaustively verifies representative market regime & direction engine scenarios:
1. Strong bullish alignment
2. Strong bearish alignment
3. Bullish structure with bearish short-term VWAP
4. Bearish structure with bullish short-term VWAP
5. Neutral/chop
6. Missing delta
7. Bar-derived delta
8. Actual delta
9. Missing sector mapping
10. Bullish 5m + bearish 15m (HTF)
11. Bearish 5m + bullish 15m (HTF)
12. High Direction Score with poor evidence coverage
13. Full evidence coverage
"""

from qx.direction.direction_engine import evaluate_direction_engine
from qx.models.rules import DeltaProvenance, GammaRegime, SessionRegime, TrendRegime, VolatilityRegime
from qx.regime.market_regime import evaluate_market_regime


def test_characterization_scenarios():
    # 1. Strong Bullish Alignment
    reg_1 = evaluate_market_regime(
        structure_state="BULLISH",
        atr_percentile=80.0,
        gamma_value=500.0,
        gamma_provenance="PROVIDER_ESTIMATED_GEX",
        has_directional_auction=True,
    )
    dir_1 = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        last_event_type="BULLISH_BOS",
        price=120.0,
        vwap=115.0,
        vwap_slope=1.2,
        fast_ema=120.0,
        medium_ema=118.0,
        slow_ema=115.0,
        fast_slope=0.5,
        medium_slope=0.3,
        slow_slope=0.2,
        delta_value=150.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=100.0,
        market_alignment_score=100.0,
        htf_structure_state="BULLISH",
        market_regime=reg_1,
    )
    assert reg_1.trend == TrendRegime.TREND_UP
    assert reg_1.volatility == VolatilityRegime.EXPANDING
    assert reg_1.gamma == GammaRegime.POSITIVE_GAMMA
    assert dir_1.direction_score == 100.0
    assert dir_1.direction_label == "BULLISH"
    assert dir_1.direction_evidence_coverage == 1.00
    assert dir_1.coverage_status == "COMPLETE"
    assert dir_1.trade_state == "NONE - PLAYBOOK NOT EVALUATED IN PHASE 5"

    # 2. Strong Bearish Alignment
    reg_2 = evaluate_market_regime(
        structure_state="BEARISH",
        atr_percentile=85.0,
        gamma_value=-400.0,
        gamma_provenance="PROVIDER_ESTIMATED_GEX",
        has_directional_auction=True,
    )
    dir_2 = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BEARISH",
        last_event_type="BEARISH_BOS",
        price=100.0,
        vwap=108.0,
        vwap_slope=-1.2,
        fast_ema=100.0,
        medium_ema=104.0,
        slow_ema=108.0,
        fast_slope=-0.5,
        medium_slope=-0.3,
        slow_slope=-0.2,
        delta_value=-150.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=-100.0,
        market_alignment_score=-100.0,
        htf_structure_state="BEARISH",
        market_regime=reg_2,
    )
    assert reg_2.trend == TrendRegime.TREND_DOWN
    assert reg_2.gamma == GammaRegime.NEGATIVE_GAMMA
    assert dir_2.direction_score == -100.0
    assert dir_2.direction_label == "BEARISH"
    assert dir_2.direction_evidence_coverage == 1.00
    assert dir_2.coverage_status == "COMPLETE"
    assert dir_2.trade_state == "NONE - PLAYBOOK NOT EVALUATED IN PHASE 5"

    # 3. Bullish structure with bearish short-term VWAP
    dir_3 = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        price=110.0,
        vwap=115.0,
        vwap_slope=-0.8,
        delta_value=50.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
    )
    struct_f = next(f for f in dir_3.factors if f.factor_id == "structure")
    vwap_f = next(f for f in dir_3.factors if f.factor_id == "vwap")
    assert struct_f.raw_score == 100.0
    assert vwap_f.raw_score == -100.0
    assert dir_3.direction_score > 0

    # 4. Bearish structure with bullish short-term VWAP
    dir_4 = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BEARISH",
        price=115.0,
        vwap=110.0,
        vwap_slope=0.8,
        delta_value=-50.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
    )
    assert dir_4.direction_score < 0

    # 5. Neutral / Chop
    reg_5 = evaluate_market_regime(structure_state="NEUTRAL", atr_percentile=20.0)
    dir_5 = evaluate_direction_engine(symbol="ES", structure_state="NEUTRAL")
    assert reg_5.trend == TrendRegime.RANGE
    assert reg_5.volatility == VolatilityRegime.COMPRESSED
    assert dir_5.direction_score == 0.0
    assert dir_5.direction_label == "NEUTRAL"
    assert dir_5.coverage_status == "INSUFFICIENT"
    assert dir_5.trade_state == "NONE - PLAYBOOK NOT EVALUATED IN PHASE 5"

    # 6. Missing Delta
    dir_6 = evaluate_direction_engine(symbol="ES", delta_provenance=DeltaProvenance.UNAVAILABLE)
    delta_f6 = next(f for f in dir_6.factors if f.factor_id == "delta")
    assert delta_f6.availability == "UNAVAILABLE"
    assert delta_f6.effective_weight == 0.0

    # 7. Bar-derived Delta
    dir_7 = evaluate_direction_engine(symbol="ES", delta_value=80.0, delta_provenance=DeltaProvenance.BAR_DERIVED)
    delta_f7 = next(f for f in dir_7.factors if f.factor_id == "delta")
    assert delta_f7.reliability_multiplier == 0.40
    assert delta_f7.effective_weight == 0.15 * 0.40

    # 8. Actual Delta
    dir_8 = evaluate_direction_engine(symbol="ES", delta_value=80.0, delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR)
    delta_f8 = next(f for f in dir_8.factors if f.factor_id == "delta")
    assert delta_f8.reliability_multiplier == 1.00
    assert delta_f8.effective_weight == 0.15

    # 9. Missing Sector Mapping
    dir_9 = evaluate_direction_engine(symbol="UNMAPPED_TICKER", relative_strength_score=90.0)
    sec_f9 = next(f for f in dir_9.factors if f.factor_id == "sector_rs")
    assert sec_f9.availability == "UNAVAILABLE"

    # 10. Bullish 5m + Bearish 15m (HTF)
    dir_10 = evaluate_direction_engine(symbol="NVDA", structure_state="BULLISH", htf_structure_state="BEARISH")
    htf_f10 = next(f for f in dir_10.factors if f.factor_id == "higher_timeframe")
    assert htf_f10.raw_score == -100.0

    # 11. Bearish 5m + Bullish 15m (HTF)
    dir_11 = evaluate_direction_engine(symbol="NVDA", structure_state="BEARISH", htf_structure_state="BULLISH")
    htf_f11 = next(f for f in dir_11.factors if f.factor_id == "higher_timeframe")
    assert htf_f11.raw_score == 100.0

    # 12. High Direction Score with poor evidence coverage
    dir_12 = evaluate_direction_engine(
        symbol="UNMAPPED_TICKER",
        structure_state="BULLISH",
        delta_provenance=DeltaProvenance.UNAVAILABLE,
    )
    assert dir_12.direction_score == 100.0
    assert dir_12.direction_evidence_coverage == 0.30
    assert dir_12.coverage_status == "INSUFFICIENT"

    # 13. Full Evidence Coverage
    dir_13 = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        price=120.0,
        vwap=115.0,
        vwap_slope=1.0,
        fast_ema=120.0,
        medium_ema=118.0,
        slow_ema=115.0,
        fast_slope=0.5,
        medium_slope=0.3,
        slow_slope=0.2,
        delta_value=100.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=80.0,
        market_alignment_score=80.0,
        htf_structure_state="BULLISH",
    )
    assert dir_13.direction_evidence_coverage == 1.00
    assert dir_13.coverage_status == "COMPLETE"
    assert dir_13.trade_state == "NONE - PLAYBOOK NOT EVALUATED IN PHASE 5"
