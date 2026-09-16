"""Time-of-day normalized RVOL with deterministic same-slot caching."""

import math
from statistics import fmean, median, pstdev
from typing import Dict, Iterable, Optional, Tuple

from qx.tradeability.models import RVOLBaseline, RVOLResult

class RVOLTimezoneMismatchError(ValueError): pass
class RVOLSessionMismatchError(ValueError): pass
class RVOLLeakageError(ValueError): pass
class RVOLIdentityMismatchError(ValueError): pass
class InsufficientRVOLHistoryError(ValueError): pass



RVOLCacheKey = Tuple[str, str, str, int, str, str]


def _valid_volumes(volumes: Iterable[float]) -> list[float]:
    return [float(value) for value in volumes if math.isfinite(value) and value >= 0.0]


def build_rvol_baseline(
    *,
    symbol: str,
    timeframe: str,
    time_slot: str,
    historical_slot_volumes: Iterable[float],
    baseline_computed_at: str,
    lookback_sessions: int = 20,
    slot_timezone: str = "America/New_York",
    session_type: str = "RTH",
    baseline_session_dates: Iterable[str] = (),
) -> RVOLBaseline:
    """Build a baseline from prior valid sessions for one exact slot."""

    if lookback_sessions <= 0:
        raise ValueError("lookback_sessions must be positive")
    volumes = _valid_volumes(historical_slot_volumes)[-lookback_sessions:]
    if not volumes:
        raise ValueError("At least one valid historical same-slot volume is required")
    return RVOLBaseline(
        symbol=symbol.upper(),
        timeframe=timeframe,
        time_slot=time_slot,
        slot_mean_volume=fmean(volumes),
        slot_median_volume=median(volumes),
        slot_std=pstdev(volumes),
        baseline_sessions_used=len(volumes),
        baseline_computed_at=baseline_computed_at,
        lookback_sessions=lookback_sessions,
        historical_slot_volumes=volumes,
        slot_timezone=slot_timezone,
        session_type=session_type,
        baseline_session_dates=list(baseline_session_dates),
    )


class RVOLBaselineCache:
    """In-memory cache keyed by symbol, timeframe, slot, and lookback."""

    def __init__(self) -> None:
        self._baselines: Dict[RVOLCacheKey, RVOLBaseline] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(symbol: str, timeframe: str, time_slot: str, lookback_sessions: int, session_type: str = "RTH", slot_timezone: str = "America/New_York") -> RVOLCacheKey:
        return symbol.upper(), timeframe, time_slot, lookback_sessions, session_type, slot_timezone

    def get(self, symbol: str, timeframe: str, time_slot: str, lookback_sessions: int, session_type: str = "RTH", slot_timezone: str = "America/New_York") -> Optional[RVOLBaseline]:
        baseline = self._baselines.get(self.key(symbol, timeframe, time_slot, lookback_sessions, session_type, slot_timezone))
        if baseline is None:
            self.misses += 1
        else:
            self.hits += 1
        return baseline

    def get_or_build(
        self,
        *,
        symbol: str,
        timeframe: str,
        time_slot: str,
        historical_slot_volumes: Iterable[float],
        baseline_computed_at: str,
        lookback_sessions: int = 20,
        slot_timezone: str = "America/New_York",
        session_type: str = "RTH",
        baseline_session_dates: Iterable[str] = (),
    ) -> RVOLBaseline:
        cache_key = self.key(symbol, timeframe, time_slot, lookback_sessions, session_type, slot_timezone)
        cached = self._baselines.get(cache_key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        baseline = build_rvol_baseline(
            symbol=symbol,
            timeframe=timeframe,
            time_slot=time_slot,
            historical_slot_volumes=historical_slot_volumes,
            baseline_computed_at=baseline_computed_at,
            lookback_sessions=lookback_sessions,
            slot_timezone=slot_timezone,
            session_type=session_type,
            baseline_session_dates=baseline_session_dates,
        )
        self._baselines[cache_key] = baseline
        return baseline

    def clear(self) -> None:
        self._baselines.clear()
        self.hits = 0
        self.misses = 0


def _validate_baseline_identity(
    baseline: RVOLBaseline,
    *,
    expected_symbol: Optional[str],
    expected_timeframe: Optional[str],
    expected_time_slot: Optional[str],
    expected_timezone: Optional[str] = None,
    expected_session_type: Optional[str] = None,
    evaluation_session_date: Optional[str] = None,
) -> None:
    if expected_symbol is not None and baseline.symbol.upper() != expected_symbol.upper():
        raise RVOLIdentityMismatchError("RVOL baseline symbol does not match current evidence")
    if expected_timeframe is not None and baseline.timeframe != expected_timeframe:
        raise RVOLIdentityMismatchError("RVOL baseline timeframe does not match current evidence")
    if expected_time_slot is not None and baseline.time_slot != expected_time_slot:
        raise RVOLIdentityMismatchError("RVOL baseline time slot does not match current evidence")
    if expected_timezone is not None and baseline.slot_timezone != expected_timezone:
        raise RVOLTimezoneMismatchError("RVOL baseline timezone does not match current evidence")
    if expected_session_type is not None and baseline.session_type != expected_session_type:
        raise RVOLSessionMismatchError("RVOL baseline session type does not match current evidence")
    if evaluation_session_date and baseline.baseline_session_dates:
        if max(baseline.baseline_session_dates) >= evaluation_session_date:
            raise RVOLLeakageError("RVOL baseline leaked current evaluation session data")


def compute_rvol(
    current_volume: float,
    baseline: RVOLBaseline,
    minimum_valid_sessions: int = 10,
    *,
    expected_symbol: Optional[str] = None,
    expected_timeframe: Optional[str] = None,
    expected_time_slot: Optional[str] = None,
    expected_timezone: Optional[str] = None,
    expected_session_type: Optional[str] = None,
    evaluation_session_date: Optional[str] = None,
) -> RVOLResult:
    """Compute RVOL only against a matching historical intraday slot."""

    _validate_baseline_identity(
        baseline,
        expected_symbol=expected_symbol,
        expected_timeframe=expected_timeframe,
        expected_time_slot=expected_time_slot,
        expected_timezone=expected_timezone,
        expected_session_type=expected_session_type,
        evaluation_session_date=evaluation_session_date,
    )
    if baseline.baseline_sessions_used < minimum_valid_sessions:
        raise InsufficientRVOLHistoryError(f"Insufficient RVOL history: {baseline.baseline_sessions_used} < {minimum_valid_sessions}")

    rvol_mean = current_volume / baseline.slot_mean_volume if baseline.slot_mean_volume > 0 else 0.0
    rvol_median = current_volume / baseline.slot_median_volume if baseline.slot_median_volume > 0 else 0.0
    historical = baseline.historical_slot_volumes
    if historical:
        below = sum(value < current_volume for value in historical)
        equal = sum(value == current_volume for value in historical)
        percentile = 100.0 * (below + 0.5 * equal) / len(historical)
    elif baseline.slot_std > 0:
        z_score = (current_volume - baseline.slot_mean_volume) / baseline.slot_std
        percentile = 50.0 + 50.0 * math.erf(z_score / math.sqrt(2.0))
    elif current_volume > baseline.slot_mean_volume:
        percentile = 100.0
    elif current_volume < baseline.slot_mean_volume:
        percentile = 0.0
    else:
        percentile = 50.0

    return RVOLResult(
        current_volume=current_volume,
        slot_mean_volume=baseline.slot_mean_volume,
        slot_median_volume=baseline.slot_median_volume,
        slot_std=baseline.slot_std,
        rvol_mean_ratio=rvol_mean,
        rvol_median_ratio=rvol_median,
        volume_percentile=max(0.0, min(100.0, percentile)),
        baseline_sessions_used=baseline.baseline_sessions_used,
        time_slot=baseline.time_slot,
        normalized=True,
        slot_timezone=baseline.slot_timezone,
        session_type=baseline.session_type,
    )


def compute_rvol_optional(
    current_volume: float,
    baseline: Optional[RVOLBaseline],
    minimum_valid_sessions: int = 10,
    *,
    expected_symbol: Optional[str] = None,
    expected_timeframe: Optional[str] = None,
    expected_time_slot: Optional[str] = None,
    expected_timezone: Optional[str] = None,
    expected_session_type: Optional[str] = None,
    evaluation_session_date: Optional[str] = None,
) -> Optional[RVOLResult]:
    if baseline is None:
        return None
    return compute_rvol(
        current_volume,
        baseline,
        minimum_valid_sessions,
        expected_symbol=expected_symbol,
        expected_timeframe=expected_timeframe,
        expected_time_slot=expected_time_slot,
        expected_timezone=expected_timezone,
        expected_session_type=expected_session_type,
        evaluation_session_date=evaluation_session_date,
    )
