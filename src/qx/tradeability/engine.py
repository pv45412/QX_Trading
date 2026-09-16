"""Phase 8 tradeability engine for triggered underlying setups."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from qx.config.rules_config import RulesEngineConfig, TradeabilityConfig, load_rules_config
from qx.models.rules import DeltaProvenance, PublicationState, SignalState
from qx.tradeability.models import (
    RVOLResult,
    TradeabilityContext,
    TradeabilityMarketEvidence,
    TradeabilityReasonCode,
    TradeabilityResult,
    TradeabilityState,
)
from qx.tradeability.rvol import compute_rvol_optional
from qx.triggers.models import TriggeredSetupResult


_DEFAULT_DELTA_RELIABILITY: Dict[str, float] = {
    DeltaProvenance.ACTUAL_TRADE_AGGRESSOR.value: 1.00,
    DeltaProvenance.ESTIMATED_BID_ASK.value: 0.75,
    DeltaProvenance.BAR_DERIVED.value: 0.40,
    DeltaProvenance.UNAVAILABLE.value: 0.00,
}


def _get_delta_reliability(provenance: DeltaProvenance, reliability_map: Dict[str, float]) -> float:
    return reliability_map.get(provenance.value, 0.0)


def _delta_aligned(delta_value: Optional[float], direction: str) -> bool:
    if delta_value is None:
        return False
    return (direction == "BULLISH" and delta_value > 0) or (direction == "BEARISH" and delta_value < 0)


def _compute_delta_score(
    delta_value: Optional[float],
    provenance: DeltaProvenance,
    direction: str,
    reliability: float,
) -> float:
    if provenance == DeltaProvenance.UNAVAILABLE or not _delta_aligned(delta_value, direction):
        return 0.0
    return min(abs(float(delta_value)) / 100.0, 1.0) * 100.0 * reliability


def _compute_participation(
    rvol_result: Optional[RVOLResult],
    delta_score: float,
    delta_provenance: DeltaProvenance,
    cfg: TradeabilityConfig,
) -> Tuple[float, float]:
    weights = cfg.participation.weights
    weighted_sum = 0.0
    total_weight = 0.0
    evidence_sources_available = 0

    if rvol_result is not None and rvol_result.normalized:
        evidence_sources_available += 1
        rvol_score = min(100.0, rvol_result.rvol_mean_ratio * 50.0)
        weighted_sum += rvol_score * weights.rvol_mean_ratio
        weighted_sum += rvol_result.volume_percentile * weights.volume_percentile
        total_weight += weights.rvol_mean_ratio + weights.volume_percentile

    if delta_provenance != DeltaProvenance.UNAVAILABLE:
        evidence_sources_available += 1
        weighted_sum += delta_score * weights.delta_alignment
        total_weight += weights.delta_alignment

    if total_weight <= 0.0:
        return 0.0, 0.0
    return max(0.0, min(100.0, weighted_sum / total_weight)), evidence_sources_available / 2.0


def _compute_spread(
    bid: Optional[float],
    ask: Optional[float],
    current_price: float,
    max_spread_pct: float,
) -> Tuple[Optional[float], Optional[float], str]:
    if bid is None or ask is None:
        return None, None, "UNKNOWN"
    spread_absolute = ask - bid
    if spread_absolute < 0 or current_price <= 0:
        return spread_absolute, None, "WIDE"
    spread_pct = spread_absolute / current_price
    if spread_pct <= max_spread_pct / 2.0:
        return spread_absolute, spread_pct, "TIGHT"
    if spread_pct <= max_spread_pct:
        return spread_absolute, spread_pct, "ACCEPTABLE"
    return spread_absolute, spread_pct, "WIDE"


def _compute_extension(current_price: float, trigger_price: float, atr: float, direction: str) -> float:
    distance = current_price - trigger_price if direction == "BULLISH" else trigger_price - current_price
    return max(0.0, distance) / atr if atr > 0 else 0.0


def _compute_rr(
    current_price: float,
    invalidation_price: float,
    targets: List[float],
    direction: str,
    target_policy: str = "NEAREST_VALID_TARGET",
) -> Tuple[Optional[float], Optional[float]]:
    risk = (
        current_price - invalidation_price
        if direction == "BULLISH"
        else invalidation_price - current_price
    )
    if risk <= 0:
        return None, None
    valid_targets: List[float] = []
    for target in targets:
        if direction == "BULLISH" and target > current_price:
            valid_targets.append(target)
        if direction == "BEARISH" and target < current_price:
            valid_targets.append(target)
            
    if not valid_targets:
        return None, None
    
    # Explicitly sort targets by geometric distance to entry price
    valid_targets.sort(key=lambda t: abs(t - current_price))
    
    valid_rr = []
    for target in valid_targets:
        reward = target - current_price if direction == "BULLISH" else current_price - target
        valid_rr.append(reward / risk)
        
    rr_nearest = valid_rr[0]
    rr_best = max(valid_rr)
    
    gate_rr = rr_best if target_policy == "BEST_VALID_TARGET" else rr_nearest
    return gate_rr, rr_best


def _timeframe_seconds(timeframe: str) -> Optional[int]:
    normalized = timeframe.strip().lower()
    if normalized.endswith("m") and normalized[:-1].isdigit():
        return int(normalized[:-1]) * 60
    if normalized.endswith("h") and normalized[:-1].isdigit():
        return int(normalized[:-1]) * 3600
    return None


def _parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class TradeabilityEngine:
    """Evaluates Phase 8 only and cannot authorize execution."""

    def __init__(self, rules_config: Optional[RulesEngineConfig] = None) -> None:
        self.rules_config = rules_config or load_rules_config()

    def evaluate_triggered_setup(
        self,
        setup: TriggeredSetupResult,
        evidence: TradeabilityMarketEvidence,
        delta_reliability_map: Optional[Dict[str, float]] = None,
    ) -> TradeabilityResult:
        context = TradeabilityContext.from_triggered_setup(setup, evidence)
        return self.evaluate_tradeability(context, delta_reliability_map=delta_reliability_map)

    def evaluate_tradeability(
        self,
        ctx: TradeabilityContext,
        delta_reliability_map: Optional[Dict[str, float]] = None,
    ) -> TradeabilityResult:
        cfg = self.rules_config.tradeability
        direction_config = self.rules_config.direction_engine
        reliability_map = delta_reliability_map or dict(
            direction_config.delta_reliability or _DEFAULT_DELTA_RELIABILITY
        )
        hard_gates: Dict[str, str] = {}
        informational_reasons: List[str] = []

        def make_result(
            state: TradeabilityState,
            reason_codes: List[str],
            *,
            rvol_result: Optional[RVOLResult] = None,
            delta_score: float = 0.0,
            delta_reliability: float = 0.0,
            delta_level: Optional[float] = None,
            delta_directional_alignment: Optional[bool] = None,
            delta_change: Optional[float] = None,
            delta_slope: Optional[float] = None,
            participation_score: float = 0.0,
            participation_coverage: float = 0.0,
            extension_atr: float = 0.0,
            spread_absolute: Optional[float] = None,
            spread_pct: Optional[float] = None,
            liquidity_status: str = "UNKNOWN",
            rr_target1: Optional[float] = None,
            rr_best: Optional[float] = None,
            extra_evidence: Optional[Dict[str, Any]] = None,
        ) -> TradeabilityResult:
            evidence_ladder: Dict[str, Any] = {
                "hard_gate_outcomes": dict(hard_gates),
                "reason_codes": reason_codes,
                "bars_since_trigger": ctx.bars_since_trigger,
                "seconds_since_trigger": ctx.seconds_since_trigger,
                "quote_age_seconds": ctx.quote_age_seconds,
                "rvol_age_seconds": ctx.rvol_age_seconds,
                "delta_age_seconds": ctx.delta_age_seconds,
                "extension_atr": extension_atr,
                "gap_beyond_trigger": ctx.gap_beyond_trigger,
                "gap_distance_atr": ctx.gap_distance_atr,
                "delta_score": delta_score,
                "delta_reliability": delta_reliability,
                "participation_score": participation_score,
                "participation_coverage": participation_coverage,
            }
            if rvol_result is not None:
                evidence_ladder.update(
                    {
                        "current_volume": rvol_result.current_volume,
                        "slot_mean_volume": rvol_result.slot_mean_volume,
                        "slot_median_volume": rvol_result.slot_median_volume,
                        "slot_std": rvol_result.slot_std,
                        "rvol_mean_ratio": rvol_result.rvol_mean_ratio,
                        "rvol_median_ratio": rvol_result.rvol_median_ratio,
                        "volume_percentile": rvol_result.volume_percentile,
                        "baseline_sessions_used": rvol_result.baseline_sessions_used,
                        "rvol_normalized": rvol_result.normalized,
                    }
                )
            if spread_absolute is not None:
                evidence_ladder.update(
                    {
                        "spread_absolute": spread_absolute,
                        "spread_pct": spread_pct,
                        "liquidity_status": liquidity_status,
                    }
                )
            if rr_target1 is not None:
                evidence_ladder["rr_to_target1"] = rr_target1
            if rr_best is not None:
                evidence_ladder["rr_to_best_target"] = rr_best
            if extra_evidence:
                evidence_ladder.update(extra_evidence)
            return TradeabilityResult(
                tradeability_id=(
                    f"trade_{ctx.triggered_setup_id}_"
                    f"{ctx.evaluation_timestamp.replace(':', '').replace('-', '')}"
                ),
                triggered_setup_id=ctx.triggered_setup_id,
                playbook_id=ctx.playbook_id,
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction=ctx.direction,
                state=state,
                publication_state=ctx.publication_state,
                trigger_price=ctx.trigger_price,
                observed_underlying_price=ctx.current_price,
                observed_entry_reference_price=ctx.current_price,
                invalidation_price=ctx.invalidation_price,
                target_candidates=ctx.structural_target_candidates,
                participation_score=participation_score,
                participation_evidence_coverage=participation_coverage,
                rvol_normalized=(
                    rvol_result.rvol_mean_ratio
                    if rvol_result is not None and rvol_result.normalized
                    else None
                ),
                rvol_percentile=(
                    rvol_result.volume_percentile
                    if rvol_result is not None and rvol_result.normalized
                    else None
                ),
                delta_score=delta_score,
                delta_provenance=ctx.delta_provenance.value,
                delta_reliability=delta_reliability,
                delta_level=delta_level,
                delta_directional_alignment=delta_directional_alignment,
                delta_change=delta_change,
                delta_slope=delta_slope,
                extension_atr=extension_atr,
                spread_absolute=spread_absolute,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                risk_reward_to_target1=rr_target1,
                risk_reward_to_best_structural_target=rr_best,
                gap_beyond_trigger=ctx.gap_beyond_trigger,
                gap_distance_atr=ctx.gap_distance_atr,
                bars_since_trigger=ctx.bars_since_trigger,
                seconds_since_trigger=ctx.seconds_since_trigger,
                triggered_at=ctx.triggered_at,
                tradeability_evaluated_at=ctx.evaluation_timestamp,
                evaluated_at=ctx.evaluation_timestamp,
                data_as_of=ctx.data_as_of or ctx.evaluation_timestamp,
                reason_codes=reason_codes,
                evidence_ladder=evidence_ladder,
                config_version=self.rules_config.version,
                engine_version="v8.1.0",
            )

        if ctx.source_state != SignalState.TRIGGERED:
            hard_gates["trigger_state"] = "FAIL"
            return make_result(
                TradeabilityState.BLOCKED,
                [TradeabilityReasonCode.INVALID_TRIGGER_STATE.value],
            )
        hard_gates["trigger_state"] = "PASS"

        if ctx.publication_state == PublicationState.BLOCKED:
            hard_gates["publication_state"] = "FAIL"
            return make_result(
                TradeabilityState.BLOCKED,
                [TradeabilityReasonCode.BLOCKED_PUBLICATION_STATE.value],
            )
        hard_gates["publication_state"] = "PASS"

        if not ctx.trigger_source_still_valid:
            hard_gates["trigger_source_valid"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.TRIGGER_SOURCE_INVALID.value],
            )
        hard_gates["trigger_source_valid"] = "PASS"

        if not ctx.structure_source_still_valid:
            hard_gates["structural_source_valid"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.STRUCTURAL_SOURCE_INVALID.value],
            )
        hard_gates["structural_source_valid"] = "PASS"

        malformed_geometry = (
            ctx.direction == "BULLISH" and ctx.invalidation_price >= ctx.trigger_price
        ) or (
            ctx.direction == "BEARISH" and ctx.invalidation_price <= ctx.trigger_price
        )
        if malformed_geometry:
            hard_gates["invalidation"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.INVALID_RISK_GEOMETRY.value],
            )

        invalidation_breached = (
            ctx.direction == "BULLISH" and ctx.current_price <= ctx.invalidation_price
        ) or (
            ctx.direction == "BEARISH" and ctx.current_price >= ctx.invalidation_price
        )
        if ctx.direction not in {"BULLISH", "BEARISH"} or invalidation_breached:
            hard_gates["invalidation"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.TRIGGERED_SETUP_INVALIDATED.value],
            )
        hard_gates["invalidation"] = "PASS"

        confirmed_at = _parse_timestamp(ctx.trigger_confirmed_at)
        evaluated_at = _parse_timestamp(ctx.evaluation_timestamp)
        if (
            cfg.require_completed_bar_evidence
            and (
                not ctx.completed_bar_evidence_available
                or (confirmed_at is not None and evaluated_at is not None and evaluated_at < confirmed_at)
            )
        ):
            hard_gates["completed_evidence"] = "FAIL"
            return make_result(
                TradeabilityState.BLOCKED,
                [TradeabilityReasonCode.EVIDENCE_NOT_COMPLETE.value],
            )
        hard_gates["completed_evidence"] = "PASS"

        if ctx.quote_age_seconds > cfg.data_freshness.max_quote_age_seconds:
            hard_gates["quote_freshness"] = "FAIL"
            return make_result(
                TradeabilityState.BLOCKED,
                [TradeabilityReasonCode.STALE_MARKET_DATA.value],
                extra_evidence={"max_quote_age_seconds": cfg.data_freshness.max_quote_age_seconds},
            )
        hard_gates["quote_freshness"] = "PASS"

        max_delay_bars = cfg.max_tradeability_delay_bars.get(ctx.playbook_id, {}).get(ctx.timeframe, 3)
        timeframe_seconds = _timeframe_seconds(ctx.timeframe)
        max_delay_seconds = max_delay_bars * timeframe_seconds if timeframe_seconds is not None else None
        if ctx.bars_since_trigger > max_delay_bars or (
            max_delay_seconds is not None and ctx.seconds_since_trigger > max_delay_seconds
        ):
            hard_gates["trigger_age"] = "FAIL"
            return make_result(
                TradeabilityState.EXPIRED,
                [TradeabilityReasonCode.SETUP_EXPIRED.value],
                extra_evidence={
                    "max_tradeability_delay_bars": max_delay_bars,
                    "max_tradeability_delay_seconds": max_delay_seconds,
                },
            )
        hard_gates["trigger_age"] = "PASS"

        extension_atr = _compute_extension(
            ctx.current_price,
            ctx.trigger_price,
            ctx.atr,
            ctx.direction,
        )
        max_extension = cfg.max_extension_atr.get(ctx.playbook_id, 1.5)
        if extension_atr > max_extension:
            hard_gates["extension"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.EXCESSIVE_EXTENSION.value],
                extension_atr=extension_atr,
                extra_evidence={"max_extension_atr": max_extension},
            )
        hard_gates["extension"] = "PASS"

        if ctx.gap_beyond_trigger:
            max_gap = cfg.max_gap_distance_atr.get(ctx.playbook_id, 2.0)
            if ctx.gap_distance_atr > max_gap:
                hard_gates["gap_quality"] = "FAIL"
                return make_result(
                    TradeabilityState.NOT_TRADEABLE,
                    [TradeabilityReasonCode.GAP_TOO_LARGE.value],
                    extension_atr=extension_atr,
                    extra_evidence={"max_gap_distance_atr": max_gap},
                )
        hard_gates["gap_quality"] = "PASS"

        if ctx.liquidity_applicability == "NOT_APPLICABLE":
            hard_gates["underlying_liquidity"] = "PASS"
            spread_absolute, spread_pct, liquidity_status = None, None, "NOT_APPLICABLE"
        else:
            spread_absolute, spread_pct, liquidity_status = _compute_spread(
                ctx.bid,
                ctx.ask,
                ctx.current_price,
                cfg.underlying_spread.max_pct,
            )
            if liquidity_status == "WIDE":
                hard_gates["underlying_liquidity"] = "FAIL"
                return make_result(
                    TradeabilityState.NOT_TRADEABLE,
                    [TradeabilityReasonCode.SPREAD_TOO_WIDE.value],
                    extension_atr=extension_atr,
                    spread_absolute=spread_absolute,
                    spread_pct=spread_pct,
                    liquidity_status=liquidity_status,
                )
            if liquidity_status == "UNKNOWN":
                hard_gates["underlying_liquidity"] = "FAIL"
                return make_result(
                    TradeabilityState.BLOCKED,
                    [TradeabilityReasonCode.LIQUIDITY_UNKNOWN.value],
                    extension_atr=extension_atr,
                    spread_absolute=spread_absolute,
                    spread_pct=spread_pct,
                    liquidity_status=liquidity_status,
                )
            hard_gates["underlying_liquidity"] = "PASS"

        gate_rr, rr_best = _compute_rr(
            ctx.current_price,
            ctx.invalidation_price,
            ctx.structural_target_candidates,
            ctx.direction,
            target_policy=cfg.risk_reward.gate_target_policy.value,
        )
        if gate_rr is None:
            # Determine if invalid geometry or just no targets
            risk = (ctx.current_price - ctx.invalidation_price) if ctx.direction == "BULLISH" else (ctx.invalidation_price - ctx.current_price)
            if risk <= 0:
                reason = TradeabilityReasonCode.INVALID_RISK_GEOMETRY.value
            else:
                reason = TradeabilityReasonCode.NO_VALID_STRUCTURAL_TARGET.value
                
            hard_gates["structural_risk_reward"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [reason],
                extension_atr=extension_atr,
                spread_absolute=spread_absolute,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
            )
        minimum_rr = cfg.min_risk_reward.get(ctx.playbook_id, 1.5)
        if gate_rr < minimum_rr:
            hard_gates["structural_risk_reward"] = "FAIL"
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.INSUFFICIENT_RISK_REWARD.value],
                extension_atr=extension_atr,
                spread_absolute=spread_absolute,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                rr_target1=gate_rr,
                rr_best=rr_best,
                extra_evidence={"min_risk_reward": minimum_rr, "gate_target_policy": cfg.risk_reward.gate_target_policy.value},
            )
        hard_gates["structural_risk_reward"] = "PASS"

        rvol_fresh = (
            ctx.rvol_age_seconds is None
            or ctx.rvol_age_seconds <= cfg.data_freshness.max_rvol_age_seconds
        )
        rvol_result: Optional[RVOLResult] = None
        rvol_error: Optional[str] = None
        if rvol_fresh:
            try:
                expected_slot = ctx.current_time_slot or (
                    ctx.rvol_baseline.time_slot if ctx.rvol_baseline is not None else None
                )
                rvol_result = compute_rvol_optional(
                    ctx.current_volume,
                    ctx.rvol_baseline,
                    minimum_valid_sessions=cfg.rvol.minimum_valid_sessions,
                    expected_symbol=ctx.symbol,
                    expected_timeframe=ctx.timeframe,
                    expected_time_slot=expected_slot,
                    expected_timezone=ctx.slot_timezone,
                    expected_session_type=ctx.session_type,
                    evaluation_session_date=ctx.evaluation_session_date,
                )
            except Exception as error:
                error_type = type(error).__name__
                if error_type == "RVOLTimezoneMismatchError":
                    reason = TradeabilityReasonCode.RVOL_TIMEZONE_MISMATCH.value
                elif error_type == "RVOLSessionMismatchError":
                    reason = TradeabilityReasonCode.RVOL_SESSION_MISMATCH.value
                elif error_type == "RVOLLeakageError":
                    reason = TradeabilityReasonCode.RVOL_DATA_LEAKAGE.value
                elif error_type == "InsufficientRVOLHistoryError":
                    reason = TradeabilityReasonCode.INSUFFICIENT_RVOL_HISTORY.value
                else:
                    reason = None
                
                if reason:
                    hard_gates["rvol_validation"] = "FAIL"
                    return make_result(
                        TradeabilityState.BLOCKED,
                        [reason],
                        extra_evidence={"rvol_error": str(error)}
                    )
                rvol_error = str(error)

        delta_fresh = (
            ctx.delta_age_seconds is None
            or ctx.delta_age_seconds <= cfg.data_freshness.max_delta_age_seconds
        )
        effective_delta_provenance = (
            ctx.delta_provenance if delta_fresh else DeltaProvenance.UNAVAILABLE
        )
        delta_aligned = _delta_aligned(ctx.delta_value, ctx.direction) if delta_fresh else None
        eff_delta_level = ctx.delta_value if delta_fresh else None
        eff_delta_change = ctx.delta_change if delta_fresh else None
        eff_delta_slope = ctx.delta_slope if delta_fresh else None
        delta_reliability = _get_delta_reliability(effective_delta_provenance, reliability_map)
        delta_score = _compute_delta_score(
            ctx.delta_value if delta_fresh else None,
            effective_delta_provenance,
            ctx.direction,
            delta_reliability,
        )
        delta_conflict = (
            delta_fresh
            and ctx.delta_provenance != DeltaProvenance.UNAVAILABLE
            and ctx.delta_value is not None
            and not _delta_aligned(ctx.delta_value, ctx.direction)
        )
        if delta_conflict:
            informational_reasons.append(TradeabilityReasonCode.DELTA_CONFLICT.value)

        participation_score, participation_coverage = _compute_participation(
            rvol_result,
            delta_score,
            effective_delta_provenance,
            cfg,
        )
        minimum_coverage = cfg.min_participation_evidence_coverage.get(ctx.playbook_id, 0.0)
        if participation_coverage < minimum_coverage:
            hard_gates["participation_evidence"] = "FAIL"
            reasons = [TradeabilityReasonCode.INSUFFICIENT_PARTICIPATION_EVIDENCE.value]
            reasons.extend(informational_reasons)
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                reasons,
                rvol_result=rvol_result,
                delta_score=delta_score,
                delta_reliability=delta_reliability,
                delta_level=eff_delta_level,
                delta_directional_alignment=delta_aligned,
                delta_change=eff_delta_change,
                delta_slope=eff_delta_slope,
                participation_score=participation_score,
                participation_coverage=participation_coverage,
                extension_atr=extension_atr,
                spread_absolute=spread_absolute,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                rr_target1=gate_rr,
                rr_best=rr_best,
                extra_evidence={
                    "minimum_participation_evidence_coverage": minimum_coverage,
                    "rvol_error": rvol_error,
                    "rvol_fresh": rvol_fresh,
                    "delta_fresh": delta_fresh,
                },
            )
        hard_gates["participation_evidence"] = "PASS"

        minimum_participation = cfg.min_participation.get(ctx.playbook_id, 0.0)
        if minimum_participation > 0 and participation_score < minimum_participation:
            hard_gates["participation"] = "FAIL"
            reasons = [TradeabilityReasonCode.INSUFFICIENT_PARTICIPATION.value]
            reasons.extend(informational_reasons)
            return make_result(
                TradeabilityState.NOT_TRADEABLE,
                reasons,
                rvol_result=rvol_result,
                delta_score=delta_score,
                delta_reliability=delta_reliability,
                delta_level=eff_delta_level,
                delta_directional_alignment=delta_aligned,
                delta_change=eff_delta_change,
                delta_slope=eff_delta_slope,
                participation_score=participation_score,
                participation_coverage=participation_coverage,
                extension_atr=extension_atr,
                spread_absolute=spread_absolute,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                rr_target1=gate_rr,
                rr_best=rr_best,
                extra_evidence={
                    "min_participation": minimum_participation,
                    "rvol_error": rvol_error,
                    "rvol_fresh": rvol_fresh,
                    "delta_fresh": delta_fresh,
                },
            )
        hard_gates["participation"] = "PASS"

        reasons = [TradeabilityReasonCode.TRADEABLE_ALL_GATES_PASS.value]
        reasons.extend(informational_reasons)
        return make_result(
            TradeabilityState.TRADEABLE,
            reasons,
            rvol_result=rvol_result,
            delta_score=delta_score,
            delta_reliability=delta_reliability,
                delta_level=eff_delta_level,
                delta_directional_alignment=delta_aligned,
                delta_change=eff_delta_change,
                delta_slope=eff_delta_slope,
            participation_score=participation_score,
            participation_coverage=participation_coverage,
            extension_atr=extension_atr,
            spread_absolute=spread_absolute,
            spread_pct=spread_pct,
            liquidity_status=liquidity_status,
            rr_target1=gate_rr,
            rr_best=rr_best,
            extra_evidence={
                "rvol_error": rvol_error,
                "rvol_fresh": rvol_fresh,
                "delta_fresh": delta_fresh,
            },
        )
