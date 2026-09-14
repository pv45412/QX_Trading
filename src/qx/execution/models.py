"""Order and Execution Pydantic models for QX Platform."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    BRACKET = "BRACKET"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_TO_COVER = "BUY_TO_COVER"
    SELL_SHORT = "SELL_SHORT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class BracketParameters(BaseModel):
    take_profit_price: float = Field(..., gt=0, description="Take profit limit price")
    stop_loss_price: float = Field(..., gt=0, description="Stop loss trigger price")
    trailing_stop_pct: float | None = Field(default=None, ge=0, description="Optional trailing stop percentage")


class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, description="Ticker symbol")
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0, description="Order quantity")
    limit_price: float | None = Field(default=None, gt=0, description="Limit price for LIMIT or STOP_LIMIT orders")
    stop_price: float | None = Field(default=None, gt=0, description="Stop price for STOP or STOP_LIMIT orders")
    bracket: BracketParameters | None = Field(default=None, description="Bracket stop-loss and take-profit parameters")
    time_in_force: Literal["DAY", "GTC", "IOC", "FOK"] = "DAY"
    notes: str | None = None
    publication_state: str | None = None
    executable: bool | None = None



class ExecutionFill(BaseModel):
    fill_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    symbol: str
    side: OrderSide
    filled_quantity: float = Field(..., gt=0)
    fill_price: float = Field(..., gt=0)
    slippage: float = 0.0
    commission: float = 0.0
    filled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    limit_price: float | None = None
    stop_price: float | None = None
    bracket: BracketParameters | None = None
    status: OrderStatus = OrderStatus.PENDING
    time_in_force: str = "DAY"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fills: list[ExecutionFill] = Field(default_factory=list)
    reject_reason: str | None = None
