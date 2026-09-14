"""Signal freshness and quote latency verification engine.

Verifies signal age and quote timestamps to reject operationally stale proposals.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    WARN_LATENCY = "WARN_LATENCY"
    STALE_BLOCKED = "STALE_BLOCKED"


@dataclass(frozen=True)
class FreshnessResult:
    symbol: str
    quote_age_seconds: float
    max_threshold_seconds: float
    status: FreshnessStatus
    is_executable: bool
    reason: str


class FreshnessChecker:
    """Verifies that quotes and signals satisfy max latency constraints."""

    def __init__(
        self,
        max_intraday_age_seconds: float = 5.0,
        max_swing_age_seconds: float = 60.0,
    ) -> None:
        self.max_intraday_age_seconds = max_intraday_age_seconds
        self.max_swing_age_seconds = max_swing_age_seconds

    def check_freshness(
        self,
        symbol: str,
        quote_timestamp: datetime,
        mode: str = "swing",
        now: Optional[datetime] = None,
    ) -> FreshnessResult:
        now_dt = now or datetime.now(timezone.utc)
        ts = quote_timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        age = (now_dt - ts).total_seconds()
        max_age = (
            self.max_intraday_age_seconds
            if mode.lower() == "intraday"
            else self.max_swing_age_seconds
        )

        if age < 0:
            return FreshnessResult(
                symbol=symbol,
                quote_age_seconds=round(age, 2),
                max_threshold_seconds=max_age,
                status=FreshnessStatus.STALE_BLOCKED,
                is_executable=False,
                reason=f"Quote timestamp for {symbol} is in the future ({age:.2f}s).",
            )

        if age <= max_age:
            return FreshnessResult(
                symbol=symbol,
                quote_age_seconds=round(age, 2),
                max_threshold_seconds=max_age,
                status=FreshnessStatus.FRESH,
                is_executable=True,
                reason=f"Quote age {age:.2f}s is fresh within limit {max_age}s.",
            )
        elif age <= max_age * 2:
            return FreshnessResult(
                symbol=symbol,
                quote_age_seconds=round(age, 2),
                max_threshold_seconds=max_age,
                status=FreshnessStatus.WARN_LATENCY,
                is_executable=True,
                reason=f"Quote age {age:.2f}s exceeds target limit {max_age}s but is within tolerance window.",
            )
        else:
            return FreshnessResult(
                symbol=symbol,
                quote_age_seconds=round(age, 2),
                max_threshold_seconds=max_age,
                status=FreshnessStatus.STALE_BLOCKED,
                is_executable=False,
                reason=f"Quote age {age:.2f}s exceeds maximum stale threshold {max_age * 2}s.",
            )
