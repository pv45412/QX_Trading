"""Base abstract class for all strategy modules (Spreads, Calendars, Diagonals, LEAPs, PMCC, Wheel)."""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class StrategyContext(BaseModel):
    symbol: str
    underlying_price: float
    direction_score: float = 50.0  # 0-100
    volatility_score: float = 50.0  # 0-100
    iv_rank: float = 50.0
    expected_move_dollars: float = 0.0
    market_regime: str = "NEUTRAL"
    account_equity: float = 100000.0


class TradeProposal(BaseModel):
    strategy_name: str
    symbol: str
    expiration: str
    dte: int
    legs: list[dict[str, Any]]
    entry_debit_credit: float
    max_risk_dollars: float
    max_profit_dollars: float | None = None
    break_even_price: float
    invalidation_price: float
    target_price: float
    quality_grade: str = "B"


class BaseStrategyModule(ABC):
    """Abstract interface for all strategy modules."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the strategy (e.g. Bull Call Debit Spread)."""
        pass

    @abstractmethod
    def evaluate_compatibility(self, context: StrategyContext) -> float:
        """Return compatibility score (0.0 to 100.0) given market context."""
        pass

    @abstractmethod
    def construct_trade(self, context: StrategyContext, chain_data: dict[str, Any]) -> TradeProposal | None:
        """Construct specific trade proposal (strikes, DTE, debit/credit, max loss/profit)."""
        pass
