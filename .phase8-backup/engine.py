"""Phase 8: Tradeability Engine.

Answers: IS THIS TRIGGERED SETUP ACTUALLY TRADEABLE?

Architecture: Hard gates first, participation/quality scoring second.
High participation score can NEVER override a failed hard gate.

Hard gate evaluation order:
  1. Publication state
  2. Triggered setup source validity
  3. Data freshness (quote staleness)
  4. Trigger age (bars_since_trigger)
  5. Extension / anti-chase gate
  6. Gap quality gate
  7. Spread / liquidity gate
  8. Structural R:R gate
  9. Participation minimum gate (if configured per playbook)

Prohibited outputs:
  - SignalState.EXECUTABLE  (reserved for Phase 11)
  - Options contract fields  (Phase 9)
  - Portfolio/account risk   (Phase 10)
"""

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple

from qx.config.rules_config import RulesEngineConfig, TradeabilityConfig, load_rules_config
from qx.models.rules import DeltaProvenance, PublicationState
from qx.tradeability.models import (
    RVOLResult,
    TradeabilityContext,
    TradeabilityReasonCode,
    TradeabilityResult,
    TradeabilityState,
)
from qx.tradeability.rvol import compute_rvol_optional

# ---------------------------------------------------------------------------
# Delta reliability map (mirrors direction_engine config values)
# ---------------------------------------------------------------------------
_DEFAULT_DELTA_RELIABILITY: Dict[str, float] = {
    DeltaProvenance.ACTUAL_TRADE_AGGRESSOR.value: 1.00,
    DeltaProvenance.ESTIMATED_BID_ASK.value: 0.75,
    DeltaProvenance.BAR_DERIVED.value: 0.40,
    DeltaProvenance.UNAVAILABLE.value: 0.00,
}


def _get_delta_reliability(
    provenance: DeltaProvenance,
    reliability_map: Dict[str, float],
) -> float:
    return reliability_map.get(provenance.value, 0.0)


def _compute_delta_score(
    delta_value: Optional[float],
    provenance: DeltaProvenance,
    direction: str,
    reliability: float,
) -> float:
    """Delta alignment score (0–100), weighted by provenance reliability.

    Does NOT modify Direction Score (Phase 5 invariant preserved).
    If UNAVAILABLE: returns 0.0 (no fabrication).
    """
    if provenance == DeltaProvenance.UNAVAILABLE or delta_value is None:
        return 0.0

    is_bullish = direction == "BULLISH"
    aligned = (is_bullish and delta_value > 0) or (not is_bullish and delta_value < 0)

    if not aligned:
        return 0.0

    # Map |delta| to 0–100 (saturates at |delta| >= 100)
    raw_alignment = min(abs(delta_value) / 100.0, 1.0) * 100.0
    return raw_alignment * reliability


def _compute_participation(
    rvol_result: Optional[RVOLResult],
    delta_score: float,
    delta_provenance: DeltaProvenance,
    cfg: TradeabilityConfig,
) -> Tuple[float, float]:
    """Compute participation score (0–100) and evidence coverage (0–1).

    Components:
      - rvol_mean_ratio   (weight: cfg.participation.weights.rvol_mean_ratio)
      - delta_alignment   (weight: cfg.participation.weights.delta_alignment)
      - volume_percentile (weight: cfg.participation.weights.volume_percentile)

    Evidence coverage counts available, non-trivial evidence inputs.
    RVOL mean_ratio and volume_percentile share the same baseline (1 evidence source).
    Delta is a separate evidence source.

    Maximum evidence sources = 2 (RVOL baseline, Delta).
    coverage = available_sources / 2
    """
    weights = cfg.participation.weights
    weighted_sum = 0.0
    total_weight = 0.0
    evidence_sources_available = 0

    # --- RVOL evidence (mean_ratio + percentile from same baseline) ---
    rvol_available = rvol_result is not None and rvol_result.normalized

    if rvol_available:
        evidence_sources_available += 1

        # rvol_mean_ratio: ratio 0 = 0 pts, ratio 2.0 = 100 pts (saturates)
        rvol_score = min(100.0, rvol_result.rvol_mean_ratio * 50.0)
        weighted_sum += rvol_score * weights.rvol_mean_ratio
        total_weight += weights.rvol_mean_ratio

        # volume_percentile: 0–100 directly
        weighted_sum += rvol_result.volume_percentile * weights.volume_percentile
        total_weight += weights.volume_percentile

    # --- Delta evidence ---
    delta_available = delta_provenance != DeltaProvenance.UNAVAILABLE
    if delta_available:
        evidence_sources_available += 1
        weighted_sum += delta_score * weights.delta_alignment
        total_weight += weights.delta_alignment

    if total_weight == 0.0:
        return 0.0, 0.0

    raw_score = weighted_sum / total_weight
    score = min(100.0, max(0.0, raw_score))
    coverage = evidence_sources_available / 2.0  # 2 max sources

    return score, coverage


def _compute_spread(
    bid: Optional[float],
    ask: Optional[float],
    current_price: float,
    max_spread_pct: float,
) -> Tuple[Optional[float], Optional[float], str]:
    """Returns (spread_absolute, spread_pct, liquidity_status)."""
    if bid is None or ask is None:
        return None, None, "UNKNOWN"

    spread_abs = ask - bid
    spread_pct = spread_abs / current_price if current_price > 0 else 0.0

    if spread_pct <= max_spread_pct / 2:
        status = "TIGHT"
    elif spread_pct <= max_spread_pct:
        status = "ACCEPTABLE"
    else:
        status = "WIDE"

    return spread_abs, spread_pct, status


def _compute_extension(
    current_price: float,
    trigger_price: float,
    atr: float,
    direction: str,
) -> float:
    """Compute extension_atr: how far current_price is from trigger_price.

    Bullish: extension = (current_price - trigger_price) / ATR
    Bearish: extension = (trigger_price - current_price) / ATR

    Uses actual current_price — never assumes fill at trigger_price.
    """
    is_bullish = direction == "BULLISH"
    if is_bullish:
        distance = current_price - trigger_price
    else:
        distance = trigger_price - current_price

    distance = max(0.0, distance)  # clamp — extension is never negative
    return distance / atr if atr > 0 else 0.0


def _compute_rr(
    current_price: float,
    invalidation_price: float,
    targets: List[float],
    direction: str,
) -> Tuple[Optional[float], Optional[float]]:
    """Compute R:R using actual observed current_price as entry reference.

    Entry reference = observed_underlying_price at tradeability evaluation.
    This is NOT a fill. Options expression (Phase 9) determines actual economics.

    Returns (rr_to_target1, rr_to_best_structural_target).
    Both are None if no valid structural target provides positive R:R.
    """
    is_bullish = direction == "BULLISH"
    risk = abs(current_price - invalidation_price)

    if risk <= 0:
        return None, None

    rr_list = []
    for t in targets:
        if is_bullish:
            reward = t - current_price
        else:
            reward = current_price - t

        if reward > 0:
            rr_list.append(reward / risk)

    if not rr_list:
        return None, None

    return rr_list[0], max(rr_list)


# ---------------------------------------------------------------------------
# TradeabilityEngine
# ---------------------------------------------------------------------------

class TradeabilityEngine:
    """Phase 8: Tradeability evaluation engine.

    Thread-safe (stateless per evaluation). The engine does not cache state
    between calls; callers are responsible for caching RVOL baselines.

    Usage:
        engine = TradeabilityEngine()
        result = engine.evaluate_tradeability(ctx)
    """

    def __init__(self, rules_config: Optional[RulesEngineConfig] = None) -> None:
        self.rules_config = rules_config or load_rules_config()

    def evaluate_tradeability(
        self,
        ctx: TradeabilityContext,
        delta_reliability_map: Optional[Dict[str, float]] = None,
    ) -> TradeabilityResult:
        """Evaluate whether a TRIGGERED setup is currently tradeable.

        Hard gates are evaluated in order. The first failure returns immediately.
        Participation scoring runs only after all hard gates pass.

        Args:
            ctx: All deterministic market evidence available at evaluation time.
            delta_reliability_map: Override for delta reliability weights.
                Defaults to direction_engine.delta_reliability from config.

        Returns:
            TradeabilityResult with state, reason_codes, and evidence_ladder.
            state is NEVER SignalState.EXECUTABLE.
        """
        cfg = self.rules_config.tradeability
        de_cfg = self.rules_config.direction_engine

        rel_map = delta_reliability_map or {
            k: v for k, v in (
                de_cfg.delta_reliability.items()
                if de_cfg.delta_reliability
                else _DEFAULT_DELTA_RELIABILITY.items()
            )
        }

        eval_id = f"trade_{ctx.symbol}_{ctx.evaluation_timestamp.replace(':', '').replace('-', '')}"
        playbook_id = ctx.playbook_id
        direction = ctx.direction
        is_bullish = direction == "BULLISH"

        def _make_result(
            state: TradeabilityState,
            reason_codes: List[str],
            *,
            rvol_result: Optional[RVOLResult] = None,
            delta_score: float = 0.0,
            delta_reliability: float = 0.0,
            participation_score: float = 0.0,
            participation_coverage: float = 0.0,
            extension_atr: float = 0.0,
            spread_abs: Optional[float] = None,
            spread_pct: Optional[float] = None,
            liquidity_status: str = "UNKNOWN",
            rr_target1: Optional[float] = None,
            rr_best: Optional[float] = None,
            extra_evidence: Optional[Dict[str, Any]] = None,
        ) -> TradeabilityResult:
            evidence: Dict[str, Any] = {
                "reason_codes": reason_codes,
                "bars_since_trigger": ctx.bars_since_trigger,
                "quote_age_seconds": ctx.quote_age_seconds,
                "extension_atr": extension_atr,
                "gap_beyond_trigger": ctx.gap_beyond_trigger,
                "gap_distance_atr": ctx.gap_distance_atr,
            }
            if rvol_result:
                evidence["rvol_mean_ratio"] = rvol_result.rvol_mean_ratio
                evidence["rvol_median_ratio"] = rvol_result.rvol_median_ratio
                evidence["volume_percentile"] = rvol_result.volume_percentile
                evidence["rvol_normalized"] = rvol_result.normalized
                evidence["baseline_sessions_used"] = rvol_result.baseline_sessions_used
            evidence["delta_score"] = delta_score
            evidence["delta_reliability"] = delta_reliability
            evidence["participation_score"] = participation_score
            evidence["participation_coverage"] = participation_coverage
            if rr_target1 is not None:
                evidence["rr_to_target1"] = rr_target1
            if rr_best is not None:
                evidence["rr_to_best_target"] = rr_best
            if spread_abs is not None:
                evidence["spread_absolute"] = spread_abs
                evidence["spread_pct"] = spread_pct
                evidence["liquidity_status"] = liquidity_status
            if extra_evidence:
                evidence.update(extra_evidence)

            return TradeabilityResult(
                tradeability_id=eval_id,
                triggered_setup_id=ctx.triggered_setup_id,
                playbook_id=playbook_id,
                symbol=ctx.symbol,
                timeframe=ctx.timeframe,
                direction=direction,
                state=state,
                publication_state=ctx.publication_state,
                trigger_price=ctx.trigger_price,
                observed_underlying_price=ctx.current_price,
                invalidation_price=ctx.invalidation_price,
                target_candidates=ctx.structural_target_candidates,
                participation_score=participation_score,
                participation_evidence_coverage=participation_coverage,
                rvol_normalized=rvol_result.rvol_mean_ratio if (rvol_result and rvol_result.normalized) else None,
                rvol_percentile=rvol_result.volume_percentile if (rvol_result and rvol_result.normalized) else None,
                delta_score=delta_score,
                delta_provenance=ctx.delta_provenance.value,
                delta_reliability=delta_reliability,
                extension_atr=extension_atr,
                spread_absolute=spread_abs,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                risk_reward_to_target1=rr_target1,
                risk_reward_to_best_structural_target=rr_best,
                gap_beyond_trigger=ctx.gap_beyond_trigger,
                gap_distance_atr=ctx.gap_distance_atr,
                bars_since_trigger=ctx.bars_since_trigger,
                triggered_at=ctx.triggered_at,
                tradeability_evaluated_at=ctx.evaluation_timestamp,
                reason_codes=reason_codes,
                evidence_ladder=evidence,
                config_version=self.rules_config.version,
                engine_version="v8.0.0",
                trade_state="NONE - OPTIONS EXPRESSION NOT YET EVALUATED",
            )

        # ── Hard Gate 1: Publication State ──────────────────────────────────
        if ctx.publication_state == PublicationState.BLOCKED:
            return _make_result(
                TradeabilityState.BLOCKED,
                [TradeabilityReasonCode.BLOCKED_PUBLICATION_STATE.value],
            )

        # ── Hard Gate 2: Trigger Source Validity ────────────────────────────
        if not ctx.trigger_source_still_valid:
            return _make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.TRIGGER_SOURCE_INVALID.value],
            )

        # ── Hard Gate 3: Quote Data Freshness ───────────────────────────────
        max_age = cfg.data_freshness.max_quote_age_seconds
        if ctx.quote_age_seconds > max_age:
            return _make_result(
                TradeabilityState.BLOCKED,
                [TradeabilityReasonCode.STALE_MARKET_DATA.value],
                extra_evidence={"max_quote_age_seconds": max_age},
            )

        # ── Hard Gate 4: Trigger Age ────────────────────────────────────────
        pb_delay_map = cfg.max_tradeability_delay_bars.get(playbook_id, {})
        max_delay_bars = pb_delay_map.get(ctx.timeframe, 3)
        if ctx.bars_since_trigger > max_delay_bars:
            return _make_result(
                TradeabilityState.EXPIRED,
                [TradeabilityReasonCode.SETUP_EXPIRED.value],
                extra_evidence={"max_tradeability_delay_bars": max_delay_bars},
            )

        # ── Compute extension (needed for multiple gates/scores) ─────────────
        extension_atr = _compute_extension(
            ctx.current_price, ctx.trigger_price, ctx.atr, direction
        )

        # ── Hard Gate 5: Extension / Anti-Chase ────────────────────────────
        max_ext = cfg.max_extension_atr.get(playbook_id, 1.5)
        if extension_atr > max_ext:
            return _make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.EXCESSIVE_EXTENSION.value],
                extension_atr=extension_atr,
                extra_evidence={"max_extension_atr": max_ext},
            )

        # ── Hard Gate 6: Gap Quality ────────────────────────────────────────
        if ctx.gap_beyond_trigger:
            max_gap_atr = cfg.max_gap_distance_atr.get(playbook_id, 2.0)
            if ctx.gap_distance_atr > max_gap_atr:
                return _make_result(
                    TradeabilityState.NOT_TRADEABLE,
                    [TradeabilityReasonCode.GAP_TOO_LARGE.value],
                    extension_atr=extension_atr,
                    extra_evidence={"max_gap_distance_atr": max_gap_atr},
                )

        # ── Hard Gate 7: Spread / Liquidity ────────────────────────────────
        spread_abs, spread_pct, liquidity_status = _compute_spread(
            ctx.bid, ctx.ask, ctx.current_price, cfg.underlying_spread.max_pct
        )
        if liquidity_status == "WIDE":
            return _make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.SPREAD_TOO_WIDE.value],
                extension_atr=extension_atr,
                spread_abs=spread_abs,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
            )

        # ── Hard Gate 8: R:R ────────────────────────────────────────────────
        rr_target1, rr_best = _compute_rr(
            ctx.current_price,
            ctx.invalidation_price,
            ctx.structural_target_candidates,
            direction,
        )
        min_rr = cfg.min_risk_reward.get(playbook_id, 1.5)

        if rr_best is None:
            return _make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.NO_VALID_STRUCTURAL_TARGET.value],
                extension_atr=extension_atr,
                spread_abs=spread_abs,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
            )

        if rr_best < min_rr:
            return _make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.INSUFFICIENT_RISK_REWARD.value],
                extension_atr=extension_atr,
                spread_abs=spread_abs,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                rr_target1=rr_target1,
                rr_best=rr_best,
                extra_evidence={"min_risk_reward": min_rr},
            )

        # ── Compute RVOL ────────────────────────────────────────────────────
        rvol_result = compute_rvol_optional(
            ctx.current_volume,
            ctx.rvol_baseline,
            minimum_valid_sessions=cfg.rvol.minimum_valid_sessions,
        )

        # ── Compute Delta ───────────────────────────────────────────────────
        delta_reliability = _get_delta_reliability(ctx.delta_provenance, rel_map)
        delta_score = _compute_delta_score(
            ctx.delta_value,
            ctx.delta_provenance,
            direction,
            delta_reliability,
        )

        # ── Compute Participation ───────────────────────────────────────────
        participation_score, participation_coverage = _compute_participation(
            rvol_result, delta_score, ctx.delta_provenance, cfg
        )

        # ── Hard Gate 9: Minimum Participation (configurable per playbook) ──
        min_part = cfg.min_participation.get(playbook_id, 0.0)
        if min_part > 0 and participation_score < min_part:
            return _make_result(
                TradeabilityState.NOT_TRADEABLE,
                [TradeabilityReasonCode.INSUFFICIENT_PARTICIPATION.value],
                rvol_result=rvol_result,
                delta_score=delta_score,
                delta_reliability=delta_reliability,
                participation_score=participation_score,
                participation_coverage=participation_coverage,
                extension_atr=extension_atr,
                spread_abs=spread_abs,
                spread_pct=spread_pct,
                liquidity_status=liquidity_status,
                rr_target1=rr_target1,
                rr_best=rr_best,
                extra_evidence={"min_participation": min_part},
            )

        # ── All Hard Gates Pass → TRADEABLE ─────────────────────────────────
        return _make_result(
            TradeabilityState.TRADEABLE,
            [TradeabilityReasonCode.TRADEABLE_ALL_GATES_PASS.value],
            rvol_result=rvol_result,
            delta_score=delta_score,
            delta_reliability=delta_reliability,
            participation_score=participation_score,
            participation_coverage=participation_coverage,
            extension_atr=extension_atr,
            spread_abs=spread_abs,
            spread_pct=spread_pct,
            liquidity_status=liquidity_status,
            rr_target1=rr_target1,
            rr_best=rr_best,
        )
