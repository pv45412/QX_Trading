from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


OptionType = Literal["CALL", "PUT"]
TradeSide = Literal["AT_ASK", "AT_BID", "MID", "UNKNOWN"]
DirectionalRead = Literal["bullish", "bearish", "neutral", "hedge-risk", "spread-risk"]
FinalSignal = Literal[
    "CALLS STRONG",
    "CALLS WATCH",
    "PUTS STRONG",
    "PUTS WATCH",
    "CONFLICTED FLOW",
    "IV CHASE RISK",
    "NO TRADE",
]


class OptionFlowTrade(BaseModel):
    ticker: str
    option_symbol: str = ""
    expiration: date | None = None
    strike: float = 0.0
    option_type: OptionType = "CALL"
    trade_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    size: int = 0
    premium: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    trade_condition: str = ""
    trade_kind: str = ""
    timestamp: datetime | None = None

    @field_validator("ticker", "option_symbol", mode="before")
    @classmethod
    def _upper_text(cls, value: object) -> str:
        return str(value or "").strip().upper()

    @field_validator("option_type", mode="before")
    @classmethod
    def _option_type(cls, value: object) -> OptionType:
        text = str(value or "CALL").strip().upper()
        if text in {"C", "CALL", "CALLS"}:
            return "CALL"
        if text in {"P", "PUT", "PUTS"}:
            return "PUT"
        raise ValueError(f"Unknown option type: {value}")

    @property
    def effective_premium(self) -> float:
        if self.premium > 0:
            return self.premium
        return max(self.trade_price, 0.0) * max(self.size, 0) * 100.0

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2 if self.bid > 0 and self.ask > 0 else 0.0

    @property
    def spread_pct(self) -> float:
        midpoint = self.midpoint
        return (self.ask - self.bid) / midpoint if midpoint > 0 and self.ask >= self.bid else 1.0


class FlowClassification(BaseModel):
    trade_side: TradeSide
    aggression_score: float = Field(ge=0.0, le=100.0)
    directional_read: DirectionalRead
    bullish_score: float = Field(ge=0.0, le=100.0)
    bearish_score: float = Field(ge=0.0, le=100.0)
    risk_tags: list[str] = Field(default_factory=list)


class PremiumAnalysis(BaseModel):
    premium_score: float = Field(ge=0.0, le=100.0)
    unusual_premium_score: float = Field(ge=0.0, le=100.0)
    repeated_flow_score: float = Field(ge=0.0, le=100.0)
    ask_call_premium_score: float = Field(ge=0.0, le=100.0)
    ask_put_premium_score: float = Field(ge=0.0, le=100.0)


class IVQuality(BaseModel):
    iv_quality_score: float = Field(ge=0.0, le=100.0)
    iv_chase_risk: float = Field(ge=0.0, le=100.0)
    event_risk: bool = False
    warnings: list[str] = Field(default_factory=list)


class UnderlyingContext(BaseModel):
    ticker: str
    current_price: float = 0.0
    vwap: float = 0.0
    prior_day_high: float = 0.0
    prior_day_low: float = 0.0
    premarket_high: float = 0.0
    premarket_low: float = 0.0
    opening_range_high: float = 0.0
    opening_range_low: float = 0.0
    relative_volume: float = 1.0
    trend_direction: Literal["up", "down", "sideways", "unknown"] = "unknown"
    nearest_demand: float = 0.0
    nearest_supply: float = 0.0


class MarketRegimeContext(BaseModel):
    spy_trend: Literal["bullish", "bearish", "neutral"] = "neutral"
    qqq_trend: Literal["bullish", "bearish", "neutral"] = "neutral"
    vix_trend: Literal["rising", "falling", "flat"] = "flat"
    sector_strength: Literal["strong", "weak", "neutral"] = "neutral"
    macro_event_risk: bool = False
    market_chop: bool = False


class PriceConfirmation(BaseModel):
    call_confirmation_score: float = Field(ge=0.0, le=100.0)
    put_confirmation_score: float = Field(ge=0.0, le=100.0)
    liquidity_break_score: float = Field(ge=0.0, le=100.0)
    liquidity_breakdown_score: float = Field(ge=0.0, le=100.0)
    trigger_price: float = 0.0
    invalidation_price: float = 0.0
    notes: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    no_trade_risk: float = Field(ge=0.0, le=100.0)
    warnings: list[str] = Field(default_factory=list)


class SuggestedContract(BaseModel):
    ticker: str
    option_symbol: str
    strategy_bucket: Literal["Day Trade", "Swing Trade"]
    option_type: OptionType
    expiration: date | None
    strike: float
    delta: float
    bid: float
    ask: float
    spread_pct: float
    volume: int
    open_interest: int
    score: float
    reason: str


class DirectionScore(BaseModel):
    call_buy_score: float = Field(ge=0.0, le=100.0)
    put_buy_score: float = Field(ge=0.0, le=100.0)
    no_trade_risk: float = Field(ge=0.0, le=100.0)
    final_signal: FinalSignal
    why: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OptionFlowAnalysis(BaseModel):
    ticker: str
    current_price: float
    call_buy_score: float
    put_buy_score: float
    no_trade_risk: float
    final_signal: FinalSignal
    trigger_price: float
    invalidation_price: float
    why: list[str]
    warnings: list[str]
    trades: list[OptionFlowTrade]
    classifications: list[FlowClassification]
    suggested_contracts: list[SuggestedContract]


def clamp_score(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)
