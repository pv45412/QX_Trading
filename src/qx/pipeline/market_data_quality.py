"""Point-in-time-safe cached bar loading and market-data quality evidence."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from itertools import islice
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from qx.data.cache import _cache_symbol, validated_cache_metadata
from qx.data.cache_status import latest_completed_session
from qx.data.providers import MarketDataProvider, normalize_ohlcv
from qx.market.sessions import _schedule
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.pipeline.point_in_time import aware_utc, evaluated_bar_window_sha256


INTRADAY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
DAILY_ALIASES = {"1d", "daily"}
NEW_YORK = ZoneInfo("America/New_York")
MAX_CACHE_BYTES = 50 * 1024 * 1024
MAX_BAR_ROWS = 100_000


class MarketDataQualityStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class MarketDataQualityReport(BaseModel):
    symbol: str
    requested_timeframe: str
    observed_timeframe: str | None = None
    evaluation_timestamp: datetime
    source_file: str | None = None
    status: MarketDataQualityStatus
    publication_allowed: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    available: bool = False
    bar_count: int = 0
    usable_bar_count: int = 0
    data_as_of: datetime | None = None
    duplicate_count: int = 0
    out_of_order_count: int = 0
    missing_interval_count: int = 0
    off_session_count: int = 0
    incomplete_candle_count: int = 0
    future_bar_count: int = 0
    invalid_ohlcv_count: int = 0
    timestamp_timezone: str = "UNAVAILABLE"
    source_content_sha256: str | None = None
    source_retrieved_at: datetime | None = None


@dataclass(frozen=True)
class BarLoadOutcome:
    bars: pd.DataFrame | None
    elapsed_ms: float
    cache_hits: int
    cache_misses: int
    quality_report: MarketDataQualityReport

    def __iter__(self) -> Iterator[object]:
        yield self.bars
        yield self.elapsed_ms
        yield self.cache_hits
        yield self.cache_misses


def canonical_timeframe(timeframe: str) -> str | None:
    normalized = timeframe.strip().lower()
    if normalized in INTRADAY_MINUTES:
        return normalized
    if normalized in DAILY_ALIASES:
        return "1d"
    return None


def exact_cache_candidates(cache_dir: Path, symbol: str, timeframe: str) -> list[Path]:
    """Return candidates from only the requested timeframe class."""
    clean_symbol = _cache_symbol(symbol)
    normalized = canonical_timeframe(timeframe)
    if normalized in INTRADAY_MINUTES:
        intraday_dir = cache_dir / "intraday"
        preferred = [
            intraday_dir / f"{clean_symbol}_10d_{normalized}.csv",
            intraday_dir / f"{clean_symbol}_5d_{normalized}.csv",
        ]
        discovered = sorted(
            islice(intraday_dir.glob(f"{clean_symbol}_*_{normalized}.csv"), 32)
        )
        return list(dict.fromkeys([*preferred, *discovered]))
    if normalized == "1d":
        return [
            cache_dir / f"{clean_symbol}_1y.csv",
            cache_dir / f"{clean_symbol}_year.csv",
            cache_dir / f"{clean_symbol}_2y.csv",
        ]
    return []


def load_audited_bars(
    cache_dir: Path,
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
    active_cache_dir: Path | None = None,
) -> BarLoadOutcome:
    started = time.perf_counter()
    timestamp = aware_utc(evaluation_timestamp)
    normalized = canonical_timeframe(timeframe)
    if normalized is None:
        report = _empty_report(
            symbol,
            timeframe,
            timestamp,
            MarketDataQualityStatus.BLOCKED,
            "UNSUPPORTED_TIMEFRAME",
        )
        return _outcome(None, started, 0, 1, report)

    directories = [cache_dir]
    if active_cache_dir is not None and active_cache_dir != cache_dir:
        directories.insert(0, active_cache_dir)
    for directory in directories:
        for candidate in exact_cache_candidates(directory, symbol, normalized):
            if not candidate.exists():
                continue
            try:
                bars, report = audit_cache_file(candidate, symbol, normalized, timestamp)
            except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
                report = _empty_report(
                    symbol,
                    normalized,
                    timestamp,
                    MarketDataQualityStatus.BLOCKED,
                    f"BAR_CACHE_INVALID_{type(exc).__name__.upper()}",
                    candidate.name,
                )
                return _outcome(None, started, 1, 0, report)
            visible_bars = bars if report.publication_allowed else None
            return _outcome(visible_bars, started, 1, 0, report)

    report = _empty_report(
        symbol,
        normalized,
        timestamp,
        MarketDataQualityStatus.UNAVAILABLE,
        "REQUESTED_TIMEFRAME_UNAVAILABLE",
    )
    return _outcome(None, started, 0, 1, report)


def load_live_audited_bars(
    provider: MarketDataProvider,
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
) -> BarLoadOutcome:
    started = time.perf_counter()
    timestamp = aware_utc(evaluation_timestamp)
    normalized = canonical_timeframe(timeframe)
    provider_name = str(getattr(provider, "provider_name", "live_market_data"))
    if normalized not in {*INTRADAY_MINUTES, "1d"}:
        report = _empty_report(
            symbol,
            timeframe,
            timestamp,
            MarketDataQualityStatus.BLOCKED,
            "LIVE_TIMEFRAME_UNSUPPORTED",
            provider_name,
        )
        return _outcome(None, started, 0, 0, report)
    try:
        retrieved_at = datetime.now(timezone.utc)
        source = provider_name
        if normalized == "1d":
            bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period="1y"))
            bars, supplemented = _supplement_daily_bars(
                provider,
                bars,
                symbol,
                timestamp,
                retrieved_at,
                provider_name,
            )
            if supplemented:
                source = f"{provider_name}:daily+30m->1d"
        elif normalized == "1h":
            source_bars = provider.get_intraday_bars(
                IntradayBarDataRequest(
                    symbol=symbol,
                    period="10d",
                    interval_minutes=30,
                    include_extended_hours=False,
                )
            )
            audited_source, source_report = audit_bar_frame(
                source_bars,
                symbol,
                "30m",
                timestamp,
                source=provider_name,
                retrieved_at=retrieved_at,
            )
            if not source_report.publication_allowed:
                values = source_report.model_dump()
                values.update(
                    requested_timeframe="1h",
                    observed_timeframe="30m",
                    source_file=f"{provider_name}:30m",
                )
                report = MarketDataQualityReport(**values)
                return _outcome(None, started, 0, 0, report)
            bars = _aggregate_hourly_bars(audited_source, timestamp)
        else:
            bars = provider.get_intraday_bars(
                IntradayBarDataRequest(
                    symbol=symbol,
                    period="10d",
                    interval_minutes=INTRADAY_MINUTES[normalized],
                    include_extended_hours=False,
                )
            )
        usable, report = audit_bar_frame(
            bars,
            symbol,
            normalized,
            timestamp,
            source=(f"{provider_name}:30m->1h" if normalized == "1h" else source),
            retrieved_at=retrieved_at,
        )
    except Exception:
        report = _empty_report(
            symbol,
            normalized,
            timestamp,
            MarketDataQualityStatus.UNAVAILABLE,
            "LIVE_BAR_PROVIDER_UNAVAILABLE",
            provider_name,
        )
        return _outcome(None, started, 0, 0, report)
    visible_bars = usable if report.publication_allowed else None
    return _outcome(visible_bars, started, 0, 0, report)


def _supplement_daily_bars(
    provider: MarketDataProvider,
    daily_bars: pd.DataFrame,
    symbol: str,
    evaluation_timestamp: datetime,
    retrieved_at: datetime,
    provider_name: str,
) -> tuple[pd.DataFrame, bool]:
    expected_date = datetime.fromisoformat(
        latest_completed_session(evaluation_timestamp)
    ).date()
    daily_labels = pd.Index(pd.DatetimeIndex(daily_bars.index).date)
    if expected_date in set(daily_labels):
        return daily_bars, False
    try:
        source_bars = provider.get_intraday_bars(
            IntradayBarDataRequest(
                symbol=symbol,
                period="10d",
                interval_minutes=30,
                include_extended_hours=False,
            )
        )
        audited_source, source_report = audit_bar_frame(
            source_bars,
            symbol,
            "30m",
            evaluation_timestamp,
            source=f"{provider_name}:30m",
            retrieved_at=retrieved_at,
        )
    except Exception:
        return daily_bars, False
    if not source_report.publication_allowed:
        return daily_bars, False
    completed = _aggregate_complete_daily_sessions(
        audited_source,
        evaluation_timestamp,
    )
    expected_timestamp = pd.Timestamp(expected_date)
    if expected_timestamp not in completed.index:
        return daily_bars, False
    normalized_daily = daily_bars.copy()
    normalized_daily.index = pd.DatetimeIndex(normalized_daily.index).tz_localize(None).normalize()
    if expected_timestamp in normalized_daily.index:
        return daily_bars, False
    merged = pd.concat([normalized_daily, completed.loc[[expected_timestamp]]]).sort_index()
    return merged, True


def _aggregate_complete_daily_sessions(
    bars: pd.DataFrame,
    evaluation_timestamp: datetime,
) -> pd.DataFrame:
    if bars.empty or "timestamp" not in bars.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    timestamps = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    values = bars.drop(columns=["timestamp"]).copy()
    values.index = timestamps
    local_dates = np.asarray(timestamps.tz_convert(NEW_YORK).date)
    windows = _session_windows(evaluation_timestamp)
    interval = pd.Timedelta(minutes=30)
    rows: list[dict[str, float]] = []
    labels: list[pd.Timestamp] = []
    cutoff = pd.Timestamp(evaluation_timestamp)
    for local_date in np.unique(local_dates):
        window = windows.get(local_date)
        if window is None or window[1] > cutoff:
            continue
        selected = values.loc[local_dates == local_date]
        expected = pd.date_range(window[0], window[1] - interval, freq=interval)
        if not selected.index.equals(expected):
            continue
        rows.append(
            {
                "open": float(selected["open"].iloc[0]),
                "high": float(selected["high"].max()),
                "low": float(selected["low"].min()),
                "close": float(selected["close"].iloc[-1]),
                "volume": float(selected["volume"].sum()),
            }
        )
        labels.append(pd.Timestamp(local_date))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(labels))


def _aggregate_hourly_bars(
    bars: pd.DataFrame,
    evaluation_timestamp: datetime,
) -> pd.DataFrame:
    if bars.empty or "timestamp" not in bars.columns:
        raise ValueError("Audited 30-minute bars are unavailable")
    timestamps = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    values = bars.drop(columns=["timestamp"]).copy()
    values.index = timestamps
    windows = _session_windows(evaluation_timestamp)
    rows: list[dict[str, float]] = []
    starts: list[pd.Timestamp] = []
    local_dates = np.asarray(timestamps.tz_convert(NEW_YORK).date)
    for local_date in np.unique(local_dates):
        window = windows.get(local_date)
        if window is None:
            continue
        selected = values.loc[local_dates == local_date]
        offsets = ((selected.index - window[0]) // pd.Timedelta(hours=1)).astype(int)
        for offset in sorted(set(offsets)):
            bucket = selected.loc[offsets == offset]
            start = window[0] + pd.Timedelta(hours=int(offset))
            expected = pd.DatetimeIndex([start, start + pd.Timedelta(minutes=30)])
            if len(bucket) != 2 or not bucket.index.equals(expected):
                continue
            rows.append(
                {
                    "open": float(bucket["open"].iloc[0]),
                    "high": float(bucket["high"].max()),
                    "low": float(bucket["low"].min()),
                    "close": float(bucket["close"].iloc[-1]),
                    "volume": float(bucket["volume"].sum()),
                }
            )
            starts.append(start)
    if not rows:
        raise ValueError("No complete session-aligned hourly bars")
    return pd.DataFrame(rows, index=pd.DatetimeIndex(starts))


def audit_cache_file(
    path: Path,
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
) -> tuple[pd.DataFrame, MarketDataQualityReport]:
    normalized = canonical_timeframe(timeframe)
    if normalized is None:
        raise ValueError("Unsupported timeframe")
    if path.stat().st_size > MAX_CACHE_BYTES:
        raise ValueError("Cache exceeds audited size limit")
    raw = pd.read_csv(path)
    if raw.empty:
        raise ValueError("Empty cache")
    if len(raw) > MAX_BAR_ROWS:
        raise ValueError("Cache exceeds audited row limit")
    timestamp_column = _timestamp_column(raw)
    timestamp_index = _parse_timestamps(raw[timestamp_column])
    metadata = validated_cache_metadata(path)
    provenance = metadata.get("provenance") if metadata is not None else None
    retrieved_at = (
        datetime.fromisoformat(str(provenance["retrieved_at"]))
        if isinstance(provenance, dict) and provenance.get("retrieved_at")
        else None
    )
    bar_values = raw.drop(columns=[timestamp_column]).copy()
    return _audit_bar_values(
        bar_values,
        timestamp_index,
        symbol,
        normalized,
        evaluation_timestamp,
        source_file=path.name,
        source_content_sha256=(
            str(metadata["content_sha256"]) if metadata is not None else None
        ),
        source_retrieved_at=retrieved_at,
        observed_timeframe=_observed_timeframe(path),
    )


def audit_bar_frame(
    bars: pd.DataFrame,
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
    *,
    source: str,
    retrieved_at: datetime,
) -> tuple[pd.DataFrame, MarketDataQualityReport]:
    normalized = canonical_timeframe(timeframe)
    if normalized is None:
        raise ValueError("Unsupported timeframe")
    if bars.empty:
        raise ValueError("Empty live bars")
    if len(bars) > MAX_BAR_ROWS:
        raise ValueError("Live bars exceed audited row limit")
    timestamp_index = pd.DatetimeIndex(bars.index)
    return _audit_bar_values(
        bars.copy(),
        timestamp_index,
        symbol,
        normalized,
        evaluation_timestamp,
        source_file=source,
        source_retrieved_at=aware_utc(retrieved_at),
    )


def _audit_bar_values(
    bar_values: pd.DataFrame,
    timestamp_index: pd.DatetimeIndex,
    symbol: str,
    normalized: str,
    evaluation_timestamp: datetime,
    *,
    source_file: str,
    source_content_sha256: str | None = None,
    source_retrieved_at: datetime | None = None,
    observed_timeframe: str | None = None,
) -> tuple[pd.DataFrame, MarketDataQualityReport]:
    report = MarketDataQualityReport(
        symbol=symbol.upper(),
        requested_timeframe=normalized,
        observed_timeframe=observed_timeframe or normalized,
        evaluation_timestamp=aware_utc(evaluation_timestamp),
        source_file=source_file,
        status=MarketDataQualityStatus.BLOCKED,
        available=True,
        bar_count=len(bar_values),
        duplicate_count=int(timestamp_index.duplicated().sum()),
        out_of_order_count=_out_of_order_count(timestamp_index),
        invalid_ohlcv_count=_invalid_ohlcv_count(bar_values),
        timestamp_timezone=str(timestamp_index.tz) if timestamp_index.tz is not None else "NAIVE",
        source_content_sha256=source_content_sha256,
        source_retrieved_at=source_retrieved_at,
    )
    reasons: list[str] = []
    if report.observed_timeframe != normalized:
        reasons.append("TIMEFRAME_CROSS_CONTAMINATION")
    if report.duplicate_count:
        reasons.append("DUPLICATE_BARS")
    if report.out_of_order_count:
        reasons.append("OUT_OF_ORDER_BARS")
    if report.invalid_ohlcv_count:
        reasons.append("INVALID_OHLCV")

    if report.invalid_ohlcv_count:
        values = report.model_dump()
        values["reason_codes"] = list(dict.fromkeys(reasons))
        return pd.DataFrame(), MarketDataQualityReport(**values)

    bar_values.index = timestamp_index
    bars = normalize_ohlcv(bar_values)
    if normalized in INTRADAY_MINUTES:
        usable, measurements, intraday_reasons = _audit_intraday(
            bars,
            timestamp_index,
            INTRADAY_MINUTES[normalized],
            report.evaluation_timestamp,
        )
    else:
        usable, measurements, intraday_reasons = _audit_daily(
            bars,
            timestamp_index,
            report.evaluation_timestamp,
        )
    reasons.extend(intraday_reasons)
    values = report.model_dump()
    values.update(measurements)
    values["reason_codes"] = list(dict.fromkeys(reasons))
    blocking = any(
        reason
        not in {
            "INCOMPLETE_CURRENT_CANDLE_EXCLUDED",
            "INCOMPLETE_DAILY_CANDLE_EXCLUDED",
        }
        for reason in values["reason_codes"]
    )
    values["publication_allowed"] = not blocking and not usable.empty
    values["status"] = (
        MarketDataQualityStatus.BLOCKED
        if blocking or usable.empty
        else MarketDataQualityStatus.PARTIAL
        if values["reason_codes"]
        else MarketDataQualityStatus.PASS
    )
    values["usable_bar_count"] = len(usable)
    if (
        values["publication_allowed"]
        and values["source_content_sha256"] is None
        and not usable.empty
    ):
        values["source_content_sha256"] = evaluated_bar_window_sha256(
            usable,
            normalized,
        )
    if usable.empty and "NO_COMPLETE_BARS_AT_EVALUATION_TIMESTAMP" not in values["reason_codes"]:
        values["reason_codes"].append("NO_COMPLETE_BARS_AT_EVALUATION_TIMESTAMP")
        values["publication_allowed"] = False
        values["status"] = MarketDataQualityStatus.BLOCKED
    report = MarketDataQualityReport(**values)
    return usable, report


def _audit_intraday(
    bars: pd.DataFrame,
    raw_timestamps: pd.DatetimeIndex,
    interval_minutes: int,
    evaluation_timestamp: datetime,
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    reasons: list[str] = []
    measurements: dict[str, object] = {
        "missing_interval_count": 0,
        "off_session_count": 0,
        "incomplete_candle_count": 0,
        "future_bar_count": 0,
        "data_as_of": None,
    }
    if raw_timestamps.tz is None:
        reasons.append("TIMESTAMP_TIMEZONE_UNAVAILABLE")
        return pd.DataFrame(columns=bars.columns), measurements, reasons

    timestamps = raw_timestamps.tz_convert(timezone.utc)
    cutoff = pd.Timestamp(evaluation_timestamp)
    interval = pd.Timedelta(minutes=interval_minutes)
    future = timestamps > cutoff
    incomplete = (timestamps <= cutoff) & ((timestamps + interval) > cutoff)
    measurements["future_bar_count"] = int(future.sum())
    measurements["incomplete_candle_count"] = int(incomplete.sum())
    if future.any():
        reasons.append("FUTURE_BARS_EXCLUDED")
    if incomplete.any():
        reasons.append("INCOMPLETE_CURRENT_CANDLE_EXCLUDED")

    complete_mask = ~(future | incomplete)
    complete_timestamps = timestamps[complete_mask]
    usable = bars.loc[complete_mask].copy().reset_index(drop=True)
    if len(complete_timestamps):
        usable["timestamp"] = complete_timestamps
        measurements["data_as_of"] = complete_timestamps.max().to_pydatetime()

    off_session = _off_session_count(complete_timestamps, evaluation_timestamp)
    measurements["off_session_count"] = off_session
    if off_session:
        reasons.append("OUTSIDE_REGULAR_SESSION")

    missing = _missing_intraday_intervals(
        complete_timestamps,
        interval_minutes,
        evaluation_timestamp,
    )
    measurements["missing_interval_count"] = missing
    if missing:
        reasons.append("MISSING_INTRADAY_BARS")

    if _intraday_cadence_mismatch(
        complete_timestamps,
        interval_minutes,
        evaluation_timestamp,
    ):
        reasons.append("TIMEFRAME_CADENCE_MISMATCH")

    expected = _latest_completed_intraday_start(evaluation_timestamp, interval_minutes)
    data_as_of = measurements["data_as_of"]
    if expected is not None and (data_as_of is None or pd.Timestamp(data_as_of) < expected):
        reasons.append("STALE_BARS")
    return usable, measurements, reasons


def _audit_daily(
    bars: pd.DataFrame,
    raw_timestamps: pd.DatetimeIndex,
    evaluation_timestamp: datetime,
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    reasons: list[str] = []
    expected = latest_completed_session(evaluation_timestamp)
    labels = pd.Index(raw_timestamps.date)
    expected_date = datetime.fromisoformat(expected).date()
    evaluation_date = evaluation_timestamp.astimezone(NEW_YORK).date()
    future = labels > evaluation_date
    incomplete = (labels > expected_date) & ~future
    incomplete_count = int(incomplete.sum())
    future_count = int(future.sum())
    if incomplete_count:
        reasons.append("INCOMPLETE_DAILY_CANDLE_EXCLUDED")
    if future_count:
        reasons.append("FUTURE_BARS_EXCLUDED")
    complete_mask = np.asarray(labels <= expected_date)
    usable = bars.loc[complete_mask].copy().reset_index(drop=True)
    complete_labels = labels[complete_mask]
    duplicate_dates = int(complete_labels.duplicated().sum())
    if duplicate_dates:
        reasons.append("DAILY_SESSION_DUPLICATES")
    valid_sessions = _daily_session_dates(labels, evaluation_timestamp)
    if any(label not in valid_sessions for label in labels):
        reasons.append("NON_SESSION_DAILY_BAR")
    missing = _missing_daily_sessions(complete_labels, evaluation_timestamp)
    if missing:
        reasons.append("MISSING_DAILY_BARS")
    data_as_of = None
    if len(complete_labels):
        last_label = complete_labels[-1]
        data_as_of = datetime.combine(last_label, datetime.min.time(), tzinfo=timezone.utc)
        usable["timestamp"] = pd.to_datetime(complete_labels, utc=True)
        if last_label < expected_date:
            reasons.append("STALE_BARS")
    else:
        reasons.append("STALE_BARS")
    measurements: dict[str, object] = {
        "missing_interval_count": missing,
        "off_session_count": 0,
        "incomplete_candle_count": incomplete_count,
        "future_bar_count": future_count,
        "data_as_of": data_as_of,
    }
    return usable, measurements, reasons


def _timestamp_column(frame: pd.DataFrame) -> object:
    for column in frame.columns:
        normalized = str(column).strip().lower()
        if normalized in {"date", "datetime", "timestamp", "time"} or normalized.startswith(
            "unnamed"
        ):
            return column
    raise ValueError("Timestamp column unavailable")


def _parse_timestamps(values: pd.Series) -> pd.DatetimeIndex:
    text = values.astype("string").str.strip()
    aware_mask = text.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True, na=False)
    if aware_mask.any() and not aware_mask.all():
        raise ValueError("Mixed naive and timezone-aware timestamps")
    try:
        parsed = pd.to_datetime(
            text,
            errors="raise",
            format="mixed",
            utc=bool(aware_mask.all()),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid timestamps") from exc
    if parsed.isna().any():
        raise ValueError("Invalid timestamps")
    return pd.DatetimeIndex(parsed)


def _observed_timeframe(path: Path) -> str | None:
    stem = path.stem.lower()
    for timeframe in INTRADAY_MINUTES:
        if stem.endswith(f"_{timeframe}"):
            return timeframe
    if stem.endswith(("_1y", "_year", "_2y")):
        return "1d"
    return None


def _invalid_ohlcv_count(frame: pd.DataFrame) -> int:
    columns = {str(column).strip().lower(): column for column in frame.columns}
    required = ["open", "high", "low", "close", "volume"]
    if not all(column in columns for column in required):
        return len(frame)
    values = pd.DataFrame(
        {column: pd.to_numeric(frame[columns[column]], errors="coerce") for column in required}
    )
    prices = values[["open", "high", "low", "close"]]
    invalid = (
        ~np.isfinite(values.to_numpy()).all(axis=1)
        | prices.le(0).any(axis=1)
        | values["volume"].lt(0)
        | values["high"].lt(prices.max(axis=1))
        | values["low"].gt(prices.min(axis=1))
    )
    return int(invalid.sum())


def _out_of_order_count(timestamps: pd.DatetimeIndex) -> int:
    if len(timestamps) < 2:
        return 0
    return sum(current < previous for previous, current in zip(timestamps[:-1], timestamps[1:]))


def _off_session_count(timestamps: pd.DatetimeIndex, as_of: datetime) -> int:
    if timestamps.empty:
        return 0
    schedule = _schedule(as_of.astimezone(NEW_YORK).date())
    windows = {
        timestamp.date(): (row["market_open"], row["market_close"])
        for timestamp, row in schedule.iterrows()
    }
    local_dates = np.asarray(timestamps.tz_convert(NEW_YORK).date)
    count = 0
    for local_date in np.unique(local_dates):
        mask = local_dates == local_date
        window = windows.get(local_date)
        if window is None:
            count += int(mask.sum())
        else:
            selected = timestamps[mask]
            count += int(((selected < window[0]) | (selected >= window[1])).sum())
    return count


def _missing_intraday_intervals(
    timestamps: pd.DatetimeIndex,
    interval_minutes: int,
    as_of: datetime,
) -> int:
    if not len(timestamps):
        return 0
    ordered = pd.DatetimeIndex(timestamps.unique()).sort_values()
    local_dates = np.asarray(ordered.tz_convert(NEW_YORK).date)
    windows = _session_windows(as_of)
    interval = pd.Timedelta(minutes=interval_minutes)
    first_date = min(local_dates)
    last_date = max(local_dates)
    latest_completed = _latest_completed_intraday_start(as_of, interval_minutes)
    missing = 0
    for local_date in np.unique(local_dates):
        window = windows.get(local_date)
        if window is None:
            continue
        selected = ordered[local_dates == local_date]
        final_start = window[1] - interval
        if latest_completed is not None and local_date == as_of.astimezone(NEW_YORK).date():
            final_start = min(final_start, latest_completed)
        initial_start = window[0]
        if local_date == first_date and local_date != last_date:
            initial_start = max(initial_start, selected.min())
        expected = pd.date_range(initial_start, final_start, freq=interval)
        missing += len(expected.difference(selected))
    return missing


def _intraday_cadence_mismatch(
    timestamps: pd.DatetimeIndex,
    interval_minutes: int,
    as_of: datetime,
) -> bool:
    if not len(timestamps):
        return False
    ordered = pd.DatetimeIndex(timestamps.unique()).sort_values()
    local_dates = np.asarray(ordered.tz_convert(NEW_YORK).date)
    windows = _session_windows(as_of)
    interval = pd.Timedelta(minutes=interval_minutes)
    for local_date in np.unique(local_dates):
        window = windows.get(local_date)
        if window is None:
            continue
        selected = ordered[local_dates == local_date]
        expected = pd.date_range(window[0], window[1] - interval, freq=interval)
        expected_values = set(expected)
        if any(timestamp not in expected_values for timestamp in selected):
            return True
    return False


def _latest_completed_intraday_start(
    evaluation_timestamp: datetime, interval_minutes: int
) -> pd.Timestamp | None:
    cutoff = pd.Timestamp(evaluation_timestamp)
    schedule = _schedule(evaluation_timestamp.astimezone(NEW_YORK).date())
    interval = pd.Timedelta(minutes=interval_minutes)
    eligible = schedule.loc[schedule["market_open"] + interval <= cutoff]
    if eligible.empty:
        return None
    row = eligible.iloc[-1]
    effective_end = min(cutoff, row["market_close"])
    completed = int((effective_end - row["market_open"]) // interval)
    if completed < 1:
        return None
    return row["market_open"] + ((completed - 1) * interval)


def _session_windows(as_of: datetime) -> dict[object, tuple[pd.Timestamp, pd.Timestamp]]:
    schedule = _schedule(as_of.astimezone(NEW_YORK).date())
    return {
        timestamp.date(): (row["market_open"], row["market_close"])
        for timestamp, row in schedule.iterrows()
    }


def _missing_daily_sessions(labels: pd.Index, as_of: datetime) -> int:
    if len(labels) < 2:
        return 0
    observed = set(labels)
    expected = {
        session
        for session in _daily_session_dates(labels, as_of)
        if labels[0] <= session <= labels[-1]
    }
    return len(expected.difference(observed))


def _daily_session_dates(labels: pd.Index, as_of: datetime) -> set[object]:
    if not len(labels):
        return set()
    start_date = min(labels)
    end_date = max(max(labels), as_of.astimezone(NEW_YORK).date())
    return set(_daily_session_dates_for_range(start_date, end_date))


@lru_cache(maxsize=64)
def _daily_session_dates_for_range(start_date: date, end_date: date) -> frozenset[date]:
    schedule = mcal.get_calendar("NYSE").schedule(start_date=start_date, end_date=end_date)
    return frozenset(timestamp.date() for timestamp in schedule.index)


def _empty_report(
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
    status: MarketDataQualityStatus,
    reason_code: str,
    source_file: str | None = None,
) -> MarketDataQualityReport:
    return MarketDataQualityReport(
        symbol=symbol.upper(),
        requested_timeframe=timeframe,
        evaluation_timestamp=evaluation_timestamp,
        source_file=source_file,
        status=status,
        reason_codes=[reason_code],
    )


def _outcome(
    bars: pd.DataFrame | None,
    started: float,
    hits: int,
    misses: int,
    report: MarketDataQualityReport,
) -> BarLoadOutcome:
    return BarLoadOutcome(
        bars=bars,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
        cache_hits=hits,
        cache_misses=misses,
        quality_report=report,
    )
