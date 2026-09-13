from datetime import date

from pydantic import BaseModel, Field


class BarDataRequest(BaseModel):
    symbol: str
    start: date | None = None
    end: date | None = None
    period: str = "1y"


class IntradayBarDataRequest(BaseModel):
    symbol: str
    period: str = "5d"
    interval_minutes: int = Field(default=5, ge=1)
    include_extended_hours: bool = False


class MarketDataMetadata(BaseModel):
    symbol: str
    rows: int = Field(ge=0)
    provider: str
