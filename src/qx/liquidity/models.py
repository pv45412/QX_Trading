from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LiquidityLevel:
    symbol: str
    price: float
    label: str
    side: str
    source: str
    score: float
    distance_pct: float
    note: str


@dataclass(frozen=True)
class OptionWall:
    symbol: str
    expiration: str
    strike: float
    side: str
    open_interest: int
    volume: int
    implied_volatility: float
    score: float
    distance_pct: float


@dataclass(frozen=True)
class LiquiditySnapshot:
    symbol: str
    data_symbol: str
    asset_type: str
    current_price: float
    bias: str
    nearest_support: LiquidityLevel | None
    nearest_resistance: LiquidityLevel | None
    top_call_wall: OptionWall | None
    top_put_wall: OptionWall | None
    levels: list[LiquidityLevel] = field(default_factory=list)
    option_walls: list[OptionWall] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
