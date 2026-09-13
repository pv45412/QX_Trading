"""Position Health Score Engine for QX Platform.

Calculates multi-factor health scores (0-100) and maps scores to actionable position actions:
STRONG HOLD, HOLD, TIGHTEN, TRIM, EXIT, ROLL.
"""

from typing import Any, Literal
import numpy as np
from pydantic import BaseModel, Field


class HealthBreakdown(BaseModel):
    trend_score: float = Field(ge=0.0, le=100.0)
    structure_score: float = Field(ge=0.0, le=100.0)
    invalidation_distance_score: float = Field(ge=0.0, le=100.0)
    reward_remaining_score: float = Field(ge=0.0, le=100.0)
    momentum_score: float = Field(ge=0.0, le=100.0)
    volatility_score: float = Field(ge=0.0, le=100.0)
    operations_risk_score: float = Field(ge=0.0, le=100.0)


class PositionHealthResult(BaseModel):
    composite_score: float = Field(ge=0.0, le=100.0)
    action: Literal["STRONG HOLD", "HOLD", "HOLD / TIGHTEN", "TRIM / ADJUST", "EXIT / REVIEW", "ROLL / CLOSE"]
    hard_override_active: bool = False
    override_reason: str | None = None
    breakdown: HealthBreakdown


def calculate_position_health(
    trend_score: float,
    structure_score: float,
    invalidation_distance_pct: float,
    reward_remaining_pct: float,
    momentum_score: float,
    volatility_score: float,
    dte: int,
    stop_breached: bool = False,
    assignment_imminent: bool = False,
) -> PositionHealthResult:
    """Calculate multi-factor position health score and lifecycle recommendation.

    :param trend_score: 0-100 alignment score
    :param structure_score: 0-100 structure quality score (BOS/CHoCH/FVG support)
    :param invalidation_distance_pct: % distance price is away from stop loss / invalidation level
    :param reward_remaining_pct: % of initial max profit potential remaining
    :param momentum_score: 0-100 momentum/RSI alignment score
    :param volatility_score: 0-100 IV/HV favorable state score
    :param dte: Days to expiration
    :param stop_breached: Hard override flag if stop loss was invalidated
    :param assignment_imminent: Hard override flag if option assignment risk is acute
    """
    # Hard override checks first
    if stop_breached:
        breakdown = HealthBreakdown(
            trend_score=trend_score,
            structure_score=structure_score,
            invalidation_distance_score=0.0,
            reward_remaining_score=reward_remaining_pct,
            momentum_score=momentum_score,
            volatility_score=volatility_score,
            operations_risk_score=0.0,
        )
        return PositionHealthResult(
            composite_score=0.0,
            action="EXIT / REVIEW",
            hard_override_active=True,
            override_reason="Stop loss level invalidated",
            breakdown=breakdown,
        )

    if assignment_imminent:
        breakdown = HealthBreakdown(
            trend_score=trend_score,
            structure_score=structure_score,
            invalidation_distance_score=max(0.0, min(100.0, invalidation_distance_pct * 10.0)),
            reward_remaining_score=reward_remaining_pct,
            momentum_score=momentum_score,
            volatility_score=volatility_score,
            operations_risk_score=10.0,
        )
        return PositionHealthResult(
            composite_score=25.0,
            action="ROLL / CLOSE",
            hard_override_active=True,
            override_reason="Option assignment operational risk elevated",
            breakdown=breakdown,
        )

    # Normalize invalidation distance score (e.g. 5% distance -> 100 score, 0% -> 0 score)
    invalidation_score = max(0.0, min(100.0, invalidation_distance_pct * 20.0))
    # Normalize reward remaining score
    reward_score = max(0.0, min(100.0, reward_remaining_pct))

    # Expiration operations risk score
    if dte <= 2:
        ops_score = 20.0
    elif dte <= 7:
        ops_score = 60.0
    else:
        ops_score = 100.0

    breakdown = HealthBreakdown(
        trend_score=float(np.clip(trend_score, 0, 100)),
        structure_score=float(np.clip(structure_score, 0, 100)),
        invalidation_distance_score=float(np.clip(invalidation_score, 0, 100)),
        reward_remaining_score=float(np.clip(reward_score, 0, 100)),
        momentum_score=float(np.clip(momentum_score, 0, 100)),
        volatility_score=float(np.clip(volatility_score, 0, 100)),
        operations_risk_score=float(np.clip(ops_score, 0, 100)),
    )

    # Weighted model (Section 7)
    composite = (
        0.20 * breakdown.trend_score
        + 0.20 * breakdown.structure_score
        + 0.15 * breakdown.invalidation_distance_score
        + 0.15 * breakdown.reward_remaining_score
        + 0.10 * breakdown.momentum_score
        + 0.10 * breakdown.volatility_score
        + 0.10 * breakdown.operations_risk_score
    )

    # Map composite score to lifecycle recommendation
    if composite >= 85.0:
        action = "STRONG HOLD"
    elif composite >= 70.0:
        action = "HOLD"
    elif composite >= 55.0:
        action = "HOLD / TIGHTEN"
    elif composite >= 40.0:
        action = "TRIM / ADJUST"
    else:
        action = "EXIT / REVIEW"

    return PositionHealthResult(
        composite_score=round(composite, 2),
        action=action,
        hard_override_active=False,
        override_reason=None,
        breakdown=breakdown,
    )
