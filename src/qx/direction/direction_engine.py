"""Phase 5B: Direction Engine.

Produces a deterministic directional score bounded strictly between -100 and +100.
Combines 7 weighted directional factors:
1. Structure (0.30)
2. VWAP (0.15)
3. EMA (0.10)
4. Delta (0.15)
5. Sector Relative Strength (0.10)
6. Market Alignment (0.10)
7. Higher Timeframe (0.10)

Does NOT include RVOL, spread, liquidity, risk/reward, options IV, or portfolio risk.
Provenance-aware reliability & factor freshness scale factor weights without redistributing missing weights.
Emits NO trade signals. Coverage statuses use neutral evidence-quality terminology (INSUFFICIENT, PARTIAL, ADEQUATE, STRONG, COMPLETE).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from qx.config.rules_config import (
    DirectionEngineConfig,
    FreshnessConfig,
    RulesEngineConfig,
    StructureScoresConfig,
    load_rules_config,
)
from qx.models.rules import DeltaProvenance, EvidenceCoverageStatus, FreshnessStatus, MarketRegimeModel


class DirectionFactor(BaseModel):
    factor_id: str
    factor_name: str
    evidence_family: str = ""
    raw_score: float = Field(ge=-100.0, le=100.0)
    normalized_score: float = Field(ge=-100.0, le=100.0)
    configured_weight: float = Field(ge=0.0, le=1.0)
    availability: str = "AVAILABLE"  # "AVAILABLE" or "UNAVAILABLE"
    provenance: str = "BAR_DERIVED"
    reliability_multiplier: float = Field(default=1.0, ge=0.0, le=1.0)
    effective_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    weighted_contribution: float = 0.0
    data_as_of: str = ""
    age_seconds: Optional[float] = None
    age_bars: Optional[int] = None
    freshness_status: str = "FRESH"  # "FRESH", "STALE", "UNAVAILABLE"
    event_timestamp: str = ""
    knowledge_timestamp: str = ""
    detail: str = ""


class DirectionEngineResult(BaseModel):
    symbol: str
    timeframe: str
    direction_score: float = Field(ge=-100.0, le=100.0)
    direction_label: str  # "BULLISH", "LEAN_BULLISH", "NEUTRAL", "LEAN_BEARISH", "BEARISH"
    direction_evidence_coverage: float = Field(ge=0.0, le=1.0)
    coverage_status: str  # "COMPLETE", "STRONG", "ADEQUATE", "PARTIAL", "INSUFFICIENT"
    trade_state: str = "NONE - PLAYBOOK NOT EVALUATED IN PHASE 5"
    factors: List[DirectionFactor] = Field(default_factory=list)
    total_effective_weight: float = Field(ge=0.0, le=1.0)
    total_configured_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    config_version: str = "research_v1"
    engine_version: str = "v5.1.0"
    event_timestamp: str = ""
    knowledge_timestamp: str = ""


def compute_structure_factor(
    structure_result: Optional[Any] = None,
    structure_state: Optional[str] = None,
    last_event_type: Optional[str] = None,
    timeframe: str = "5m",
    age_bars: Optional[int] = None,
    configured_weight: float = 0.30,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    """Computes Structure Factor contribution driven by configuration structure scores and freshness."""
    scores = config.structure_scores if config else StructureScoresConfig()
    fresh_cfg = config.freshness if config else FreshnessConfig()

    state_str = None
    if structure_result is not None:
        if hasattr(structure_result, "regime"):
            s_val = getattr(structure_result, "regime")
            state_str = s_val.value if hasattr(s_val, "value") else str(s_val)
        elif hasattr(structure_result, "state"):
            s_val = getattr(structure_result, "state")
            state_str = s_val.value if hasattr(s_val, "value") else str(s_val)
        elif isinstance(structure_result, dict):
            state_val = structure_result.get("regime", structure_result.get("state"))
            if state_val is not None:
                state_str = state_val.value if hasattr(state_val, "value") else str(state_val)
        if hasattr(structure_result, "last_event_type"):
            last_event_type = getattr(structure_result, "last_event_type")
        elif hasattr(structure_result, "latest_event"):
            latest_event = getattr(structure_result, "latest_event")
            if latest_event is not None:
                last_event_type = getattr(latest_event, "event_type", last_event_type)
        if hasattr(structure_result, "age_bars"):
            age_bars = getattr(structure_result, "age_bars")
    if state_str is None and structure_state is not None:
        state_str = str(structure_state)

    state_str = (state_str or "NEUTRAL").upper()
    event_type = (last_event_type or "").upper()

    if state_str == "BULLISH":
        if "CHOCH" in event_type:
            raw_score = scores.bullish_choch
            detail = f"Bullish CHoCH event confirmed ({scores.bullish_choch})"
        elif "INITIAL_BREAK" in event_type:
            raw_score = scores.bullish_initial_break
            detail = f"Bullish Initial Break event confirmed ({scores.bullish_initial_break})"
        else:
            raw_score = scores.bullish_bos
            detail = f"Bullish BOS continuation confirmed ({scores.bullish_bos})"
    elif state_str == "BEARISH":
        if "CHOCH" in event_type:
            raw_score = scores.bearish_choch
            detail = f"Bearish CHoCH event confirmed ({scores.bearish_choch})"
        elif "INITIAL_BREAK" in event_type:
            raw_score = scores.bearish_initial_break
            detail = f"Bearish Initial Break event confirmed ({scores.bearish_initial_break})"
        else:
            raw_score = scores.bearish_bos
            detail = f"Bearish BOS continuation confirmed ({scores.bearish_bos})"
    else:
        raw_score = scores.neutral
        detail = "Structure neutral"

    # Freshness check
    max_bars = fresh_cfg.structure_max_age_bars.get(timeframe, 25)
    freshness = FreshnessStatus.FRESH.value
    reliability = 1.00

    if age_bars is not None and age_bars > max_bars:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier
        detail += f" [STALE: age_bars {age_bars} > max {max_bars}]"

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="structure",
        factor_name="Market Structure",
        evidence_family="market_structure",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance="CONFIRMED_SMC",
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_bars=age_bars,
        freshness_status=freshness,
        detail=detail,
    )


def compute_vwap_factor(
    price: Optional[float] = None,
    vwap: Optional[float] = None,
    vwap_slope: Optional[float] = None,
    age_seconds: Optional[float] = None,
    configured_weight: float = 0.15,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    """Computes VWAP Factor based on price position, slope, alignment, and freshness."""
    if price is None or vwap is None:
        return DirectionFactor(
            factor_id="vwap",
            factor_name="VWAP Alignment",
            evidence_family="vwap",
            raw_score=0.0,
            normalized_score=0.0,
            configured_weight=configured_weight,
            availability="UNAVAILABLE",
            provenance="BAR_DERIVED",
            reliability_multiplier=0.0,
            effective_weight=0.0,
            weighted_contribution=0.0,
            freshness_status=FreshnessStatus.UNAVAILABLE.value,
            detail="VWAP or price unavailable",
        )

    slope = vwap_slope if vwap_slope is not None else 0.0

    if price > vwap and slope > 0:
        raw_score = 100.0
        detail = f"Price ({price}) above VWAP ({vwap}) with rising slope"
    elif price < vwap and slope < 0:
        raw_score = -100.0
        detail = f"Price ({price}) below VWAP ({vwap}) with falling slope"
    elif price > vwap and slope < 0:
        raw_score = 30.0
        detail = f"Price ({price}) above VWAP ({vwap}) but slope falling"
    elif price < vwap and slope > 0:
        raw_score = -30.0
        detail = f"Price ({price}) below VWAP ({vwap}) but slope rising"
    else:
        raw_score = 0.0
        detail = "Price equal to VWAP or flat slope"

    fresh_cfg = config.freshness if config else FreshnessConfig()
    max_sec = fresh_cfg.quote_max_age_seconds
    freshness = FreshnessStatus.FRESH.value
    reliability = 1.00

    if age_seconds is not None and age_seconds > max_sec:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier
        detail += f" [STALE: age {age_seconds:.1f}s > max {max_sec}s]"

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="vwap",
        factor_name="VWAP Alignment",
        evidence_family="vwap",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance="BAR_DERIVED",
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_seconds=age_seconds,
        freshness_status=freshness,
        detail=detail,
    )


def compute_ema_factor(
    fast_ema: Optional[float] = None,
    medium_ema: Optional[float] = None,
    slow_ema: Optional[float] = None,
    fast_slope: Optional[float] = None,
    medium_slope: Optional[float] = None,
    slow_slope: Optional[float] = None,
    age_seconds: Optional[float] = None,
    configured_weight: float = 0.10,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    """Computes EMA Factor using stack order, slope alignment, and freshness."""
    if fast_ema is None or medium_ema is None or slow_ema is None:
        return DirectionFactor(
            factor_id="ema",
            factor_name="EMA Alignment",
            evidence_family="ema",
            raw_score=0.0,
            normalized_score=0.0,
            configured_weight=configured_weight,
            availability="UNAVAILABLE",
            provenance="BAR_DERIVED",
            reliability_multiplier=0.0,
            effective_weight=0.0,
            weighted_contribution=0.0,
            freshness_status=FreshnessStatus.UNAVAILABLE.value,
            detail="EMA values unavailable",
        )

    f_slope = fast_slope if fast_slope is not None else 0.0
    m_slope = medium_slope if medium_slope is not None else 0.0
    s_slope = slow_slope if slow_slope is not None else 0.0

    is_bull_stack = fast_ema > medium_ema > slow_ema
    is_bear_stack = fast_ema < medium_ema < slow_ema

    all_slopes_pos = f_slope > 0 and m_slope > 0 and s_slope > 0
    all_slopes_neg = f_slope < 0 and m_slope < 0 and s_slope < 0

    if is_bull_stack and all_slopes_pos:
        raw_score = 100.0
        detail = "Perfect bullish EMA stack with positive slopes"
    elif is_bull_stack:
        raw_score = 60.0
        detail = "Bullish EMA stack with mixed slopes"
    elif is_bear_stack and all_slopes_neg:
        raw_score = -100.0
        detail = "Perfect bearish EMA stack with negative slopes"
    elif is_bear_stack:
        raw_score = -60.0
        detail = "Bearish EMA stack with mixed slopes"
    else:
        raw_score = 0.0
        detail = "Mixed EMA stack near neutral"

    fresh_cfg = config.freshness if config else FreshnessConfig()
    max_sec = fresh_cfg.quote_max_age_seconds
    freshness = FreshnessStatus.FRESH.value
    reliability = 1.00

    if age_seconds is not None and age_seconds > max_sec:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier
        detail += f" [STALE: age {age_seconds:.1f}s > max {max_sec}s]"

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="ema",
        factor_name="EMA Alignment",
        evidence_family="ema",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance="BAR_DERIVED",
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_seconds=age_seconds,
        freshness_status=freshness,
        detail=detail,
    )


def compute_delta_factor(
    delta_value: Optional[float] = None,
    delta_provenance: Optional[DeltaProvenance | str] = None,
    age_seconds: Optional[float] = None,
    configured_weight: float = 0.15,
    reliability_config: Optional[Dict[str, float]] = None,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    """Computes Delta Factor with provenance-aware reliability and freshness."""
    prov_str = delta_provenance.value if isinstance(delta_provenance, DeltaProvenance) else str(delta_provenance or "UNAVAILABLE")

    if reliability_config is None:
        reliability_config = {
            "ACTUAL_TRADE_AGGRESSOR": 1.00,
            "ESTIMATED_BID_ASK": 0.75,
            "BAR_DERIVED": 0.40,
            "UNAVAILABLE": 0.00,
        }

    reliability = reliability_config.get(prov_str, 0.0)

    if delta_value is None or prov_str == "UNAVAILABLE" or reliability == 0.0:
        return DirectionFactor(
            factor_id="delta",
            factor_name="Order Flow Delta",
            evidence_family="delta",
            raw_score=0.0,
            normalized_score=0.0,
            configured_weight=configured_weight,
            availability="UNAVAILABLE",
            provenance="UNAVAILABLE",
            reliability_multiplier=0.0,
            effective_weight=0.0,
            weighted_contribution=0.0,
            freshness_status=FreshnessStatus.UNAVAILABLE.value,
            detail="Delta unavailable",
        )

    raw_score = max(-100.0, min(100.0, delta_value))

    fresh_cfg = config.freshness if config else FreshnessConfig()
    max_sec = fresh_cfg.quote_max_age_seconds
    freshness = FreshnessStatus.FRESH.value

    if age_seconds is not None and age_seconds > max_sec:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="delta",
        factor_name="Order Flow Delta",
        evidence_family="delta",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance=prov_str,
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_seconds=age_seconds,
        freshness_status=freshness,
        detail=f"Delta={delta_value:.1f} with provenance {prov_str} (reliability={reliability:.2f})",
    )


def compute_sector_rs_factor(
    symbol: str,
    relative_strength_score: Optional[float] = None,
    sector_benchmarks: Optional[Dict[str, str]] = None,
    age_seconds: Optional[float] = None,
    configured_weight: float = 0.10,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    """Computes Sector Relative Strength Factor for equities against benchmark.

    Belongs to evidence family: sector_relative_strength
    """
    if sector_benchmarks is None:
        sector_benchmarks = {"NVDA": "XLK", "AAPL": "XLK", "MSFT": "XLK", "JPM": "XLF", "XOM": "XLE"}

    benchmark = sector_benchmarks.get(symbol)

    if benchmark is None or relative_strength_score is None:
        return DirectionFactor(
            factor_id="sector_rs",
            factor_name="Sector Relative Strength",
            evidence_family="sector_relative_strength",
            raw_score=0.0,
            normalized_score=0.0,
            configured_weight=configured_weight,
            availability="UNAVAILABLE",
            provenance="UNAVAILABLE",
            reliability_multiplier=0.0,
            effective_weight=0.0,
            weighted_contribution=0.0,
            freshness_status=FreshnessStatus.UNAVAILABLE.value,
            detail=f"No sector mapping or RS data available for {symbol}",
        )

    raw_score = max(-100.0, min(100.0, relative_strength_score))

    fresh_cfg = config.freshness if config else FreshnessConfig()
    max_sec = fresh_cfg.quote_max_age_seconds
    freshness = FreshnessStatus.FRESH.value
    reliability = 1.00

    if age_seconds is not None and age_seconds > max_sec:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="sector_rs",
        factor_name="Sector Relative Strength",
        evidence_family="sector_relative_strength",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance=f"BENCHMARK_{benchmark}",
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_seconds=age_seconds,
        freshness_status=freshness,
        detail=f"Relative strength vs {benchmark}: {raw_score:.1f}",
    )


def compute_market_alignment_factor(
    symbol: str,
    market_alignment_score: Optional[float] = None,
    is_index_future: bool = False,
    age_seconds: Optional[float] = None,
    configured_weight: float = 0.10,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    """Computes Market Alignment Factor (e.g. symbol vs SPY/QQQ).

    Belongs to evidence family: broad_market_alignment
    Avoids self-referential duplication for index futures (e.g. ES, NQ, SPX).
    """
    if is_index_future or market_alignment_score is None:
        return DirectionFactor(
            factor_id="market_alignment",
            factor_name="Broad Market Alignment",
            evidence_family="broad_market_alignment",
            raw_score=0.0,
            normalized_score=0.0,
            configured_weight=configured_weight,
            availability="UNAVAILABLE",
            provenance="UNAVAILABLE",
            reliability_multiplier=0.0,
            effective_weight=0.0,
            weighted_contribution=0.0,
            freshness_status=FreshnessStatus.UNAVAILABLE.value,
            detail=f"Market alignment unavailable or self-referential for {symbol}",
        )

    raw_score = max(-100.0, min(100.0, market_alignment_score))

    fresh_cfg = config.freshness if config else FreshnessConfig()
    max_sec = fresh_cfg.quote_max_age_seconds
    freshness = FreshnessStatus.FRESH.value
    reliability = 1.00

    if age_seconds is not None and age_seconds > max_sec:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="market_alignment",
        factor_name="Broad Market Alignment",
        evidence_family="broad_market_alignment",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance="BROAD_MARKET",
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_seconds=age_seconds,
        freshness_status=freshness,
        detail=f"Market alignment score: {raw_score:.1f}",
    )


def compute_higher_timeframe_factor(
    htf_structure_state: Optional[str] = None,
    timeframe: str = "5m",
    age_bars: Optional[int] = None,
    configured_weight: float = 0.10,
    config: Optional[DirectionEngineConfig] = None,
) -> DirectionFactor:
    state_str = str(htf_structure_state).upper() if htf_structure_state is not None else None
    if state_str is None or state_str in ("UNKNOWN", "UNAVAILABLE", "NONE", ""):
        return DirectionFactor(
            factor_id="higher_timeframe",
            factor_name="Higher Timeframe Structure",
            evidence_family="higher_timeframe_structure",
            raw_score=0.0,
            normalized_score=0.0,
            configured_weight=configured_weight,
            availability="UNAVAILABLE",
            provenance="UNAVAILABLE",
            reliability_multiplier=0.0,
            effective_weight=0.0,
            weighted_contribution=0.0,
            freshness_status=FreshnessStatus.UNAVAILABLE.value,
            detail="Higher timeframe structure unavailable",
        )

    if state_str == "BULLISH":
        raw_score = 100.0
    elif state_str == "BEARISH":
        raw_score = -100.0
    else:
        raw_score = 0.0

    fresh_cfg = config.freshness if config else FreshnessConfig()
    max_bars = fresh_cfg.structure_max_age_bars.get(timeframe, 25)
    freshness = FreshnessStatus.FRESH.value
    reliability = 1.00

    if age_bars is not None and age_bars > max_bars:
        freshness = FreshnessStatus.STALE.value
        reliability *= fresh_cfg.stale_reliability_multiplier

    eff_weight = configured_weight * reliability

    return DirectionFactor(
        factor_id="higher_timeframe",
        factor_name="Higher Timeframe Structure",
        evidence_family="higher_timeframe_structure",
        raw_score=raw_score,
        normalized_score=raw_score,
        configured_weight=configured_weight,
        availability="AVAILABLE",
        provenance="CONFIRMED_HTF_SMC",
        reliability_multiplier=reliability,
        effective_weight=eff_weight,
        weighted_contribution=raw_score * eff_weight,
        age_bars=age_bars,
        freshness_status=freshness,
        detail=f"HTF confirmed structure state: {state_str}",
    )


def compute_direction_label(score: float, config: Optional[DirectionEngineConfig] = None) -> str:
    """Maps score to descriptive label based on configuration thresholds.

    - +60 to +100: BULLISH
    - +20 to +59: LEAN_BULLISH
    - -19 to +19: NEUTRAL
    - -20 to -59: LEAN_BEARISH
    - -60 to -100: BEARISH
    """
    if config is None:
        b_min = 60.0
        lb_min = 20.0
        be_max = -60.0
        lbe_max = -20.0
    else:
        b_min = config.labels.bullish_min
        lb_min = config.labels.lean_bullish_min
        be_max = config.labels.bearish_max
        lbe_max = config.labels.lean_bearish_max

    if score >= b_min:
        return "BULLISH"
    elif score >= lb_min:
        return "LEAN_BULLISH"
    elif score <= be_max:
        return "BEARISH"
    elif score <= lbe_max:
        return "LEAN_BEARISH"
    else:
        return "NEUTRAL"


def compute_coverage_status(coverage: float, config: Optional[DirectionEngineConfig] = None) -> str:
    """Calculates evidence coverage quality status using neutral terminology.

    Mapping:
    - coverage >= 0.85 -> COMPLETE
    - 0.80 <= coverage < 0.85 -> STRONG
    - 0.75 <= coverage < 0.80 -> ADEQUATE
    - 0.60 <= coverage < 0.75 -> PARTIAL
    - coverage < 0.60 -> INSUFFICIENT
    """
    if config is None:
        comp_gate = 0.85
        strong_gate = 0.80
        adeq_gate = 0.75
        part_gate = 0.60
    else:
        comp_gate = config.evidence_coverage.complete
        strong_gate = config.evidence_coverage.strong
        adeq_gate = config.evidence_coverage.adequate
        part_gate = config.evidence_coverage.partial

    if coverage >= comp_gate:
        return EvidenceCoverageStatus.COMPLETE.value
    elif coverage >= strong_gate:
        return EvidenceCoverageStatus.STRONG.value
    elif coverage >= adeq_gate:
        return EvidenceCoverageStatus.ADEQUATE.value
    elif coverage >= part_gate:
        return EvidenceCoverageStatus.PARTIAL.value
    else:
        return EvidenceCoverageStatus.INSUFFICIENT.value


def evaluate_direction_engine(
    symbol: str = "ES",
    timeframe: str = "5m",
    structure_result: Optional[Any] = None,
    structure_state: Optional[str] = None,
    last_event_type: Optional[str] = None,
    structure_age_bars: Optional[int] = None,
    price: Optional[float] = None,
    vwap: Optional[float] = None,
    vwap_slope: Optional[float] = None,
    vwap_age_seconds: Optional[float] = None,
    fast_ema: Optional[float] = None,
    medium_ema: Optional[float] = None,
    slow_ema: Optional[float] = None,
    fast_slope: Optional[float] = None,
    medium_slope: Optional[float] = None,
    slow_slope: Optional[float] = None,
    ema_age_seconds: Optional[float] = None,
    delta_value: Optional[float] = None,
    delta_provenance: Optional[DeltaProvenance | str] = None,
    delta_age_seconds: Optional[float] = None,
    relative_strength_score: Optional[float] = None,
    sector_rs_age_seconds: Optional[float] = None,
    market_alignment_score: Optional[float] = None,
    market_alignment_age_seconds: Optional[float] = None,
    is_index_future: bool = False,
    htf_structure_state: Optional[str] = None,
    htf_age_bars: Optional[int] = None,
    rules_config: Optional[RulesEngineConfig] = None,
    market_regime: Optional[MarketRegimeModel] = None,
) -> DirectionEngineResult:
    """Evaluates the 7 directional factors and computes Direction Score & Evidence Coverage.

    Deterministic score formula:
    weighted_sum = Σ(normalized_factor_score × configured_weight × reliability)
    effective_weight = Σ(configured_weight × reliability for available factors)
    direction_score = clamp(-100.0, weighted_sum / effective_weight, 100.0)

    Evidence Coverage formula:
    direction_evidence_coverage = total_effective_weight / total_configured_weight (1.00)

    Emits NO trade signals. Coverage status uses neutral terminology.
    """
    if rules_config is None:
        rules_config = load_rules_config()

    config = rules_config.direction_engine
    weights = config.weights

    factors: List[DirectionFactor] = [
        compute_structure_factor(
            structure_result=structure_result,
            structure_state=structure_state,
            last_event_type=last_event_type,
            timeframe=timeframe,
            age_bars=structure_age_bars,
            configured_weight=weights.structure,
            config=config,
        ),
        compute_vwap_factor(
            price=price,
            vwap=vwap,
            vwap_slope=vwap_slope,
            age_seconds=vwap_age_seconds,
            configured_weight=weights.vwap,
            config=config,
        ),
        compute_ema_factor(
            fast_ema=fast_ema,
            medium_ema=medium_ema,
            slow_ema=slow_ema,
            fast_slope=fast_slope,
            medium_slope=medium_slope,
            slow_slope=slow_slope,
            age_seconds=ema_age_seconds,
            configured_weight=weights.ema,
            config=config,
        ),
        compute_delta_factor(
            delta_value=delta_value,
            delta_provenance=delta_provenance,
            age_seconds=delta_age_seconds,
            configured_weight=weights.delta,
            reliability_config=config.delta_reliability,
            config=config,
        ),
        compute_sector_rs_factor(
            symbol=symbol,
            relative_strength_score=relative_strength_score,
            sector_benchmarks=config.sector_benchmarks,
            age_seconds=sector_rs_age_seconds,
            configured_weight=weights.sector_rs,
            config=config,
        ),
        compute_market_alignment_factor(
            symbol=symbol,
            market_alignment_score=market_alignment_score,
            is_index_future=is_index_future,
            age_seconds=market_alignment_age_seconds,
            configured_weight=weights.market_alignment,
            config=config,
        ),
        compute_higher_timeframe_factor(
            htf_structure_state=htf_structure_state,
            timeframe=timeframe,
            age_bars=htf_age_bars,
            configured_weight=weights.higher_timeframe,
            config=config,
        ),
    ]

    total_configured_weight = sum(f.configured_weight for f in factors)
    weighted_sum = sum(f.weighted_contribution for f in factors if f.availability == "AVAILABLE")
    total_effective_weight = sum(f.effective_weight for f in factors if f.availability == "AVAILABLE")

    if total_effective_weight > 0:
        raw_direction = weighted_sum / total_effective_weight
    else:
        raw_direction = 0.0

    direction_score = max(-100.0, min(100.0, raw_direction))

    coverage = total_effective_weight / total_configured_weight if total_configured_weight > 0 else 0.0
    coverage = max(0.0, min(1.0, coverage))

    label = compute_direction_label(direction_score, config=config)
    cov_status = compute_coverage_status(coverage, config=config)

    return DirectionEngineResult(
        symbol=symbol,
        timeframe=timeframe,
        direction_score=direction_score,
        direction_label=label,
        direction_evidence_coverage=coverage,
        coverage_status=cov_status,
        trade_state="NONE - PLAYBOOK NOT EVALUATED IN PHASE 5",
        factors=factors,
        total_effective_weight=total_effective_weight,
        total_configured_weight=total_configured_weight,
        config_version=rules_config.version,
        engine_version="v5.1.0",
    )
