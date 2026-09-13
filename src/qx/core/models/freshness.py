"""Data freshness and provenance models for market data."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class DataStatus(str, Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class DataFreshness(BaseModel, Generic[T]):
    """Wrapper providing source tracking and freshness state for any metric or object."""

    value: T | None = None
    source: str = "unknown"
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: DataStatus = DataStatus.LIVE
    timeframe: str | None = None
    lookback: int | None = None
    error_reason: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status in (DataStatus.LIVE, DataStatus.CACHED) and self.value is not None
