"""Pydantic models for QX Position Adjustment & Roll Engine."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class RollLeg(BaseModel):
    """Specific option order leg required to execute roll or adjustment."""
    action: Literal["BUY_TO_CLOSE", "SELL_TO_OPEN", "BUY_TO_OPEN", "SELL_TO_CLOSE"]
    option_type: Literal["call", "put", "underlying"]
    strike: float
    dte: int
    estimated_premium: float


class PositionRollRecommendation(BaseModel):
    """Evaluated roll strategy recommendation with rationale and execution legs."""
    roll_type: Literal["CREDIT_ROLL_OUT", "LEG_INTO_SPREAD", "PROTECTIVE_COLLAR", "CLOSE_POSITION", "HOLD_NO_ACTION"]
    target_dte: int
    net_credit_debit: float = Field(description="Positive = Net Credit received, Negative = Net Debit paid")
    recommended_legs: List[RollLeg]
    rationale: str


class PositionAdjustmentPlan(BaseModel):
    """Complete adjustment trade plan for an active position."""
    symbol: str
    composite_health: float
    health_action: str
    recommendation: PositionRollRecommendation


class PositionRollRequest(BaseModel):
    """API payload to request position roll & adjustment evaluation."""
    symbol: str
    underlying_price: float
    position_type: Literal["short_put", "short_call", "long_call", "long_put", "long_stock"]
    current_strike: Optional[float] = None
    current_dte: int
    current_premium: float = 0.0
    iv: float = 0.30
    trend_score: float = 60.0
    structure_score: float = 60.0
    invalidation_distance_pct: float = 3.0
    reward_remaining_pct: float = 50.0
    momentum_score: float = 60.0
    volatility_score: float = 60.0
    stop_breached: bool = False
    assignment_imminent: bool = False
