"""Phase 5A: Market Regime Engine.

Classifies the market environment independently from trade direction across four dimensions:
1. Trend Regime (TREND_UP, TREND_DOWN, RANGE)
2. Volatility Regime (COMPRESSED, NORMAL, EXPANDING)
3. Gamma Regime (POSITIVE_GAMMA, NEGATIVE_GAMMA, UNKNOWN)
4. Session Regime (OPENING, TREND_SESSION, BALANCED, LATE_SESSION)

Market Regime is descriptive and MUST NOT emit BUY/SELL signals or trade recommendations.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from qx.config.rules_config import MarketRegimeConfig, RulesEngineConfig, load_rules_config
from qx.models.rules import GammaRegime, MarketRegimeModel, SessionRegime, TrendRegime, VolatilityRegime


def classify_trend_regime(
    structure_result: Optional[Any] = None,
    structure_state: Optional[str] = None,
    invalidated: bool = False,
    alternating_breaks: bool = False,
) -> tuple[TrendRegime, Dict[str, Any]]:
    """Derives Trend Regime primarily from confirmed market structure.

    Rules:
    - TREND_UP: confirmed structural state == BULLISH and recent structure is not invalidated.
    - TREND_DOWN: confirmed structural state == BEARISH and recent structure is not invalidated.
    - RANGE: structure neutral, alternating breaks without persistent directional confirmation, or invalidated.
    """
    state_str = None
    if structure_result is not None:
        if hasattr(structure_result, "state"):
            state_val = getattr(structure_result, "state")
            state_str = state_val.value if hasattr(state_val, "value") else str(state_val)
        elif isinstance(structure_result, dict):
            state_str = str(structure_result.get("state", "NEUTRAL"))
    elif structure_state is not None:
        state_str = str(structure_state)

    state_str = (state_str or "NEUTRAL").upper()

    if state_str == "BULLISH" and not invalidated and not alternating_breaks:
        regime = TrendRegime.TREND_UP
    elif state_str == "BEARISH" and not invalidated and not alternating_breaks:
        regime = TrendRegime.TREND_DOWN
    else:
        regime = TrendRegime.RANGE

    evidence = {
        "structure_state": state_str,
        "invalidated": invalidated,
        "alternating_breaks": alternating_breaks,
        "details": f"Derived trend regime {regime.value} from structure_state={state_str}",
    }
    return regime, evidence


def classify_volatility_regime(
    atr_percentile: Optional[float] = None,
    current_atr: Optional[float] = None,
    baseline_atr: Optional[float] = None,
    realized_range_ratio: Optional[float] = None,
    config: Optional[MarketRegimeConfig] = None,
) -> tuple[VolatilityRegime, Dict[str, Any]]:
    """Derives Volatility Regime from normalized ATR percentile or baseline metrics.

    Configurable thresholds (defaults: compressed < 30, expanding > 70).
    """
    if config is None:
        config = load_rules_config().market_regime

    comp_threshold = config.volatility.compressed_percentile_max
    exp_threshold = config.volatility.expanding_percentile_min

    # Calculate percentile from ratio if percentile not explicitly provided
    computed_percentile = atr_percentile
    atr_ratio_to_baseline = None
    if current_atr is not None and baseline_atr is not None and baseline_atr > 0:
        atr_ratio_to_baseline = current_atr / baseline_atr
        if computed_percentile is None:
            # Approximate percentile mapping from ratio: ratio 1.0 -> 50 percentile
            computed_percentile = max(0.0, min(100.0, atr_ratio_to_baseline * 50.0))

    if computed_percentile is None:
        computed_percentile = 50.0  # Fallback neutral baseline

    if computed_percentile < comp_threshold:
        regime = VolatilityRegime.COMPRESSED
    elif computed_percentile > exp_threshold:
        regime = VolatilityRegime.EXPANDING
    else:
        regime = VolatilityRegime.NORMAL

    evidence = {
        "atr_percentile": computed_percentile,
        "current_atr": current_atr,
        "baseline_atr": baseline_atr,
        "atr_ratio_to_baseline": atr_ratio_to_baseline,
        "realized_range_ratio": realized_range_ratio,
        "compressed_threshold": comp_threshold,
        "expanding_threshold": exp_threshold,
        "details": f"Volatility regime {regime.value} (percentile={computed_percentile:.1f})",
    }
    return regime, evidence


def classify_gamma_regime(
    gex_data: Optional[Dict[str, Any]] = None,
    gamma_value: Optional[float] = None,
    provenance: Optional[str] = None,
) -> tuple[GammaRegime, Dict[str, Any]]:
    """Derives Gamma Regime when required options data is present and provenance is adequate.

    Taxonomy:
    - PROVIDER_ESTIMATED_GEX
    - MODEL_ESTIMATED_GEX
    - DERIVED_FROM_OPEN_INTEREST
    - UNAVAILABLE

    If data is missing or provenance is inadequate, returns UNKNOWN.
    UNKNOWN must NOT silently become POSITIVE or NEGATIVE.
    """
    if gex_data is not None:
        gamma_value = gex_data.get("gex_value", gamma_value)
        provenance = gex_data.get("gamma_provenance", provenance)
        data_as_of = gex_data.get("gamma_data_as_of", "")
        model_ver = gex_data.get("gamma_model_version", "gex_v1")
    else:
        data_as_of = ""
        model_ver = "gex_v1"

    valid_provenance = {
        "PROVIDER_ESTIMATED_GEX": "PROVIDER_ESTIMATED_GEX",
        "MODEL_ESTIMATED_GEX": "MODEL_ESTIMATED_GEX",
        "DERIVED_FROM_OPEN_INTEREST": "DERIVED_FROM_OPEN_INTEREST",
        # Map legacy/test aliases cleanly to estimated provider provenance:
        "ESTIMATED_DEALER_GEX": "PROVIDER_ESTIMATED_GEX",
        "KNOWN_DEALER_GEX": "PROVIDER_ESTIMATED_GEX",
    }

    prov_str = str(provenance) if provenance is not None else "UNAVAILABLE"
    actual_provenance = valid_provenance.get(prov_str, "UNAVAILABLE")

    if gamma_value is None or actual_provenance == "UNAVAILABLE":
        regime = GammaRegime.UNKNOWN
        actual_provenance = "UNAVAILABLE"
    elif gamma_value > 0:
        regime = GammaRegime.POSITIVE_GAMMA
    elif gamma_value < 0:
        regime = GammaRegime.NEGATIVE_GAMMA
    else:
        regime = GammaRegime.UNKNOWN

    evidence = {
        "gamma_value": gamma_value,
        "gamma_provenance": actual_provenance,
        "gamma_model_version": model_ver,
        "gamma_data_as_of": data_as_of,
        "details": f"Gamma regime {regime.value} with provenance {actual_provenance}",
    }
    return regime, evidence


def classify_session_regime(
    timestamp_str: Optional[str] = None,
    session_open_str: Optional[str] = None,
    session_close_str: Optional[str] = None,
    has_directional_auction: bool = False,
    config: Optional[MarketRegimeConfig] = None,
) -> tuple[SessionRegime, Dict[str, Any]]:
    """Derives Session Regime from time windows and auction characteristics.

    Rules:
    - OPENING: elapsed time <= opening_minutes.
    - LATE_SESSION: remaining time <= late_session_minutes.
    - TREND_SESSION: after opening, sustained directional auction / structure behavior present (requires evidence!).
    - BALANCED: main session without sustained directional auction.
    """
    if config is None:
        config = load_rules_config().market_regime

    open_mins = config.session.opening_minutes
    late_mins = config.session.late_session_minutes

    elapsed_minutes = None
    remaining_minutes = None

    if timestamp_str and session_open_str and session_close_str:
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            ts_open = datetime.fromisoformat(session_open_str.replace("Z", "+00:00"))
            ts_close = datetime.fromisoformat(session_close_str.replace("Z", "+00:00"))

            elapsed_minutes = (ts - ts_open).total_seconds() / 60.0
            remaining_minutes = (ts_close - ts).total_seconds() / 60.0
        except ValueError:
            pass

    if elapsed_minutes is not None and elapsed_minutes >= 0 and elapsed_minutes <= open_mins:
        regime = SessionRegime.OPENING
    elif remaining_minutes is not None and remaining_minutes >= 0 and remaining_minutes <= late_mins:
        regime = SessionRegime.LATE_SESSION
    else:
        # After opening window: must require market evidence, NOT clock time alone!
        if has_directional_auction:
            regime = SessionRegime.TREND_SESSION
        else:
            regime = SessionRegime.BALANCED

    evidence = {
        "elapsed_minutes": elapsed_minutes,
        "remaining_minutes": remaining_minutes,
        "opening_window_minutes": open_mins,
        "late_window_minutes": late_mins,
        "has_directional_auction": has_directional_auction,
        "details": f"Session regime {regime.value}",
    }
    return regime, evidence


def evaluate_market_regime(
    structure_result: Optional[Any] = None,
    structure_state: Optional[str] = None,
    invalidated: bool = False,
    alternating_breaks: bool = False,
    atr_percentile: Optional[float] = None,
    current_atr: Optional[float] = None,
    baseline_atr: Optional[float] = None,
    gex_data: Optional[Dict[str, Any]] = None,
    gamma_value: Optional[float] = None,
    gamma_provenance: Optional[str] = None,
    timestamp_str: Optional[str] = None,
    session_open_str: Optional[str] = None,
    session_close_str: Optional[str] = None,
    has_directional_auction: bool = False,
    data_as_of: str = "",
    rules_config: Optional[RulesEngineConfig] = None,
) -> MarketRegimeModel:
    """Evaluates all four market regime dimensions independently.

    Descriptive only - DOES NOT generate BUY/SELL signals or trade recommendations.
    """
    if rules_config is None:
        rules_config = load_rules_config()

    config = rules_config.market_regime

    trend_reg, trend_ev = classify_trend_regime(
        structure_result=structure_result,
        structure_state=structure_state,
        invalidated=invalidated,
        alternating_breaks=alternating_breaks,
    )

    vol_reg, vol_ev = classify_volatility_regime(
        atr_percentile=atr_percentile,
        current_atr=current_atr,
        baseline_atr=baseline_atr,
        config=config,
    )

    gamma_reg, gamma_ev = classify_gamma_regime(
        gex_data=gex_data,
        gamma_value=gamma_value,
        provenance=gamma_provenance,
    )

    sess_reg, sess_ev = classify_session_regime(
        timestamp_str=timestamp_str,
        session_open_str=session_open_str,
        session_close_str=session_close_str,
        has_directional_auction=has_directional_auction,
        config=config,
    )

    now_iso = datetime.now().isoformat()

    return MarketRegimeModel(
        trend=trend_reg,
        volatility=vol_reg,
        gamma=gamma_reg,
        session=sess_reg,
        trend_evidence=trend_ev,
        volatility_evidence=vol_ev,
        gamma_evidence=gamma_ev,
        session_evidence=sess_ev,
        regime_generated_at=now_iso,
        data_as_of=data_as_of or now_iso,
        config_version=rules_config.version,
        engine_version="v5.0.0",
    )
