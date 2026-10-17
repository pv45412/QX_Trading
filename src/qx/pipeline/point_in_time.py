"""Point-in-time filtering helpers shared by live and replay evaluation."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import pandas as pd


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return aware_utc(value)
    if isinstance(value, str):
        try:
            return aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def bar_timestamp(bar: Any) -> Optional[datetime]:
    for key in ("timestamp", "datetime", "time", "date"):
        if isinstance(bar, dict):
            value = bar.get(key)
        elif isinstance(bar, pd.Series):
            value = bar.get(key)
        else:
            value = getattr(bar, key, None)
        timestamp = parse_timestamp(value)
        if timestamp is not None:
            return timestamp
    if isinstance(bar, pd.Series):
        return parse_timestamp(bar.name)
    return None


def _bar_to_dict(bar: Any) -> dict[str, Any]:
    if isinstance(bar, dict):
        return dict(bar)
    if isinstance(bar, pd.Series):
        values = bar.to_dict()
        timestamp = bar_timestamp(bar)
        if timestamp is not None and not any(
            key in values for key in ("timestamp", "datetime", "time", "date")
        ):
            values["timestamp"] = timestamp
        return values
    if hasattr(bar, "model_dump"):
        return bar.model_dump()
    return {
        key: getattr(bar, key)
        for key in (
            "timestamp",
            "datetime",
            "time",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        )
        if hasattr(bar, key)
    }


def filter_bars_at_or_before(bars: Any, evaluation_timestamp: datetime) -> pd.DataFrame:
    cutoff = aware_utc(evaluation_timestamp)
    if bars is None:
        return pd.DataFrame()
    if isinstance(bars, pd.DataFrame):
        frame = bars.copy()
    else:
        frame = pd.DataFrame([_bar_to_dict(bar) for bar in bars])
    if frame.empty:
        return frame

    timestamp_column = next(
        (key for key in ("timestamp", "datetime", "time", "date") if key in frame.columns),
        None,
    )
    if timestamp_column is not None:
        timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="coerce")
        visible = timestamps.notna() & (timestamps <= cutoff)
        frame = frame.loc[visible].copy()
        frame["timestamp"] = timestamps[visible]
    elif isinstance(frame.index, pd.DatetimeIndex):
        timestamps = pd.to_datetime(frame.index, utc=True, errors="coerce")
        visible = timestamps.notna() & (timestamps <= cutoff)
        frame = frame.loc[visible].copy()
        frame["timestamp"] = timestamps[visible]
    else:
        return pd.DataFrame(columns=frame.columns)
    return frame.sort_values("timestamp", kind="stable").reset_index(drop=True)


def evaluated_bar_window_sha256(bars: pd.DataFrame, timeframe: str) -> str:
    if bars.empty:
        raise ValueError("Evaluated bar window is empty")
    required = ("timestamp", "open", "high", "low", "close", "volume")
    if any(column not in bars.columns for column in required):
        raise ValueError("Evaluated bar window is missing canonical OHLCV fields")
    timestamps = pd.to_datetime(bars["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("Evaluated bar window must be in canonical ascending order")
    records = []
    for row in bars.loc[:, required].itertuples(index=False, name=None):
        timestamp = pd.Timestamp(row[0])
        if timestamp.tzinfo is None:
            raise ValueError("Evaluated bar timestamps must be timezone-aware")
        records.append(
            {
                "timestamp": timestamp.tz_convert(timezone.utc)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )
    payload = json.dumps(
        {
            "schema_version": "qx.bar-window.v1",
            "timeframe": timeframe.lower(),
            "bars": records,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def latest_visible_snapshot(
    snapshots: Optional[Iterable[Any]],
    evaluation_timestamp: datetime,
    timestamp_field: str,
) -> Any:
    cutoff = aware_utc(evaluation_timestamp)
    selected = None
    selected_timestamp = None
    for snapshot in snapshots or ():
        snapshot_timestamp = parse_timestamp(getattr(snapshot, timestamp_field, None))
        if snapshot_timestamp is None or snapshot_timestamp > cutoff:
            continue
        retrieved_timestamp = parse_timestamp(getattr(snapshot, "retrieved_at", None))
        if retrieved_timestamp is None or retrieved_timestamp > cutoff:
            continue
        if selected_timestamp is None or snapshot_timestamp > selected_timestamp:
            selected = snapshot
            selected_timestamp = snapshot_timestamp
    return selected
