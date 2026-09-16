"""Phase 5A Unit Test Suite: Market Regime Engine.

Verifies independent 4-dimensional classification (Trend, Volatility, Gamma, Session).
Ensures regime is descriptive only and emits no trade signals or directional score overrides.
"""

from qx.config.rules_config import load_rules_config
from qx.models.rules import GammaRegime, MarketRegimeModel, SessionRegime, TrendRegime, VolatilityRegime
from qx.regime.market_regime import (
    classify_gamma_regime,
    classify_session_regime,
    classify_trend_regime,
    classify_volatility_regime,
    evaluate_market_regime,
)


def test_bullish_structure_maps_to_trend_up():
    regime, evidence = classify_trend_regime(structure_state="BULLISH", invalidated=False)
    assert regime == TrendRegime.TREND_UP
    assert evidence["structure_state"] == "BULLISH"


def test_bearish_structure_maps_to_trend_down():
    regime, evidence = classify_trend_regime(structure_state="BEARISH", invalidated=False)
    assert regime == TrendRegime.TREND_DOWN
    assert evidence["structure_state"] == "BEARISH"


def test_neutral_structure_can_map_to_range():
    regime, evidence = classify_trend_regime(structure_state="NEUTRAL")
    assert regime == TrendRegime.RANGE

    regime_alt, _ = classify_trend_regime(structure_state="BULLISH", alternating_breaks=True)
    assert regime_alt == TrendRegime.RANGE


def test_gamma_unknown_when_required_data_missing():
    regime, evidence = classify_gamma_regime(gex_data=None, gamma_value=None, provenance=None)
    assert regime == GammaRegime.UNKNOWN
    assert evidence["gamma_provenance"] == "UNAVAILABLE"

    # Incomplete provenance
    regime_unavail, _ = classify_gamma_regime(gamma_value=100.0, provenance="UNAVAILABLE")
    assert regime_unavail == GammaRegime.UNKNOWN


def test_negative_gamma_does_not_force_bearish_direction():
    regime, evidence = classify_gamma_regime(gamma_value=-500.0, provenance="ESTIMATED_DEALER_GEX")
    assert regime == GammaRegime.NEGATIVE_GAMMA
    # Evaluate full model with bullish structure + negative gamma
    model = evaluate_market_regime(
        structure_state="BULLISH",
        gamma_value=-500.0,
        gamma_provenance="ESTIMATED_DEALER_GEX",
    )
    # Trend remains TREND_UP despite NEGATIVE_GAMMA
    assert model.trend == TrendRegime.TREND_UP
    assert model.gamma == GammaRegime.NEGATIVE_GAMMA


def test_positive_gamma_does_not_force_bullish_direction():
    model = evaluate_market_regime(
        structure_state="BEARISH",
        gamma_value=750.0,
        gamma_provenance="KNOWN_DEALER_GEX",
    )
    # Trend remains TREND_DOWN despite POSITIVE_GAMMA
    assert model.trend == TrendRegime.TREND_DOWN
    assert model.gamma == GammaRegime.POSITIVE_GAMMA


def test_volatility_regime_uses_normalized_metric():
    regime_comp, ev_comp = classify_volatility_regime(atr_percentile=15.0)
    assert regime_comp == VolatilityRegime.COMPRESSED

    regime_norm, ev_norm = classify_volatility_regime(atr_percentile=50.0)
    assert regime_norm == VolatilityRegime.NORMAL

    regime_exp, ev_exp = classify_volatility_regime(atr_percentile=85.0)
    assert regime_exp == VolatilityRegime.EXPANDING

    # Ratio to baseline test
    regime_ratio, ev_ratio = classify_volatility_regime(current_atr=2.0, baseline_atr=10.0)
    assert regime_ratio == VolatilityRegime.COMPRESSED
    assert ev_ratio["atr_ratio_to_baseline"] == 0.2


def test_opening_session_classified_by_configured_window():
    open_str = "2026-09-15T09:30:00Z"
    close_str = "2026-09-15T16:00:00Z"
    ts_opening = "2026-09-15T09:45:00Z"  # 15 mins after open (<= 30 mins)

    regime, ev = classify_session_regime(
        timestamp_str=ts_opening,
        session_open_str=open_str,
        session_close_str=close_str,
    )
    assert regime == SessionRegime.OPENING
    assert ev["elapsed_minutes"] == 15.0


def test_late_session_classified_by_configured_window():
    open_str = "2026-09-15T09:30:00Z"
    close_str = "2026-09-15T16:00:00Z"
    ts_late = "2026-09-15T15:15:00Z"  # 45 mins before close (<= 60 mins)

    regime, ev = classify_session_regime(
        timestamp_str=ts_late,
        session_open_str=open_str,
        session_close_str=close_str,
    )
    assert regime == SessionRegime.LATE_SESSION
    assert ev["remaining_minutes"] == 45.0


def test_session_trend_requires_market_evidence_not_clock_only():
    open_str = "2026-09-15T09:30:00Z"
    close_str = "2026-09-15T16:00:00Z"
    ts_mid = "2026-09-15T11:30:00Z"  # 2 hours after open, 4.5 hours before close

    # Without market evidence -> BALANCED
    regime_no_ev, ev_no = classify_session_regime(
        timestamp_str=ts_mid,
        session_open_str=open_str,
        session_close_str=close_str,
        has_directional_auction=False,
    )
    assert regime_no_ev == SessionRegime.BALANCED

    # With market evidence -> TREND_SESSION
    regime_with_ev, ev_with = classify_session_regime(
        timestamp_str=ts_mid,
        session_open_str=open_str,
        session_close_str=close_str,
        has_directional_auction=True,
    )
    assert regime_with_ev == SessionRegime.TREND_SESSION


def test_market_regime_does_not_emit_trade_signal():
    model = evaluate_market_regime(
        structure_state="BULLISH",
        atr_percentile=90.0,
        gamma_value=-200.0,
        gamma_provenance="PROVIDER_ESTIMATED_GEX",
        has_directional_auction=True,
    )
    assert isinstance(model, MarketRegimeModel)
    assert not hasattr(model, "buy_signal")
    assert not hasattr(model, "sell_signal")
    assert not hasattr(model, "direction_score")


def test_gamma_estimate_not_labeled_known_without_authoritative_source():
    # If provenance is invalid or unknown or missing -> UNKNOWN regime
    regime_invalid, ev_invalid = classify_gamma_regime(gamma_value=500.0, provenance="UNKNOWN_PROVENANCE")
    assert regime_invalid == GammaRegime.UNKNOWN
    assert ev_invalid["gamma_provenance"] == "UNAVAILABLE"

    # Valid estimated provenance
    regime_valid, ev_valid = classify_gamma_regime(gamma_value=500.0, provenance="PROVIDER_ESTIMATED_GEX")
    assert regime_valid == GammaRegime.POSITIVE_GAMMA
    assert ev_valid["gamma_provenance"] == "PROVIDER_ESTIMATED_GEX"
    assert "KNOWN" not in ev_valid["gamma_provenance"]

