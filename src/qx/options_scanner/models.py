"""Pydantic V2 data contracts for QX Options Scanner V1."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class VetoReasonEnum(str, Enum):
    DATA_STALE = "DATA_STALE"
    CHAIN_INCOMPLETE = "CHAIN_INCOMPLETE"
    LIQUIDITY_OI = "LIQUIDITY_OI"
    LIQUIDITY_SPREAD = "LIQUIDITY_SPREAD"
    EVENT_BLACKOUT = "EVENT_BLACKOUT"
    EARNINGS_BLACKOUT = "EARNINGS_BLACKOUT"
    INSOLVENCY_FLAG = "INSOLVENCY_FLAG"


class OptionTypeEnum(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class UnderlyingQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    last_price: float
    bid: float
    ask: float
    volume: int
    timestamp: datetime
    is_insolvent: bool = False
    earnings_date: Optional[datetime] = None
    next_fomc_cpi_event: Optional[datetime] = None

    @property
    def mid_price(self) -> float:
        return round((self.bid + self.ask) / 2.0, 4) if (self.bid > 0 and self.ask > 0) else self.last_price


class OptionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    underlying_symbol: str
    strike: float
    expiration: str  # YYYY-MM-DD
    dte: int
    option_type: OptionTypeEnum
    bid: float
    ask: float
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    open_interest: int = 0
    volume: int = 0
    implied_volatility: float = 0.0

    @property
    def mid_price(self) -> float:
        return round((self.bid + self.ask) / 2.0, 4) if (self.bid > 0 and self.ask > 0) else self.bid

    @property
    def spread_pct(self) -> float:
        mid = self.mid_price
        if mid <= 0:
            return 1.0
        return round((self.ask - self.bid) / mid, 4)


class OptionChain(BaseModel):
    model_config = ConfigDict(frozen=True)

    underlying_symbol: str
    retrieved_at: datetime
    contracts: List[OptionContract] = Field(default_factory=list)


class VetoResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    reason: Optional[VetoReasonEnum] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class MarketBiasEnum(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class VIXTermStructureEnum(str, Enum):
    CONTANGO = "CONTANGO"
    BACKWARDATION = "BACKWARDATION"


class RegimeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: datetime
    market_bias: MarketBiasEnum = MarketBiasEnum.BULLISH
    vix_close: float = 15.0
    vix_term_structure: VIXTermStructureEnum = VIXTermStructureEnum.CONTANGO
    spx_close: float = 5000.0
    es_overnight_move_pct: float = 0.0


class ScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    config_version: str = "v1.0.0"
    passed_veto: bool
    veto_result: Optional[VetoResult] = None
    overall_score: float = 0.0
    direction_result: Optional[Any] = None
    volatility_result: Optional[Any] = None
    strategy_result: Optional[Any] = None
    trade: Optional[Any] = None
    risk_result: Optional[Any] = None

