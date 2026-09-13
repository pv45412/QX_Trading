"""Source-attributed daily trend snapshots for a user-defined eleven-symbol basket."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, cast

import pandas as pd

from qx.data.providers import MarketDataProvider
from qx.models.market import BarDataRequest


SCHEMA_VERSION = "qx.mag11-daily-trend.v1"


@dataclass(frozen=True)
class Mag11TrendRow:
    symbol: str
    close: float | None
    return_1d: float | None
    return_5d: float | None
    actual_source: str
    fallback_used: bool | None
    retrieved_at: str | None
    last_bar_label: str | None
    state: str


@dataclass(frozen=True)
class Mag11TrendSnapshot:
    schema_version: str
    basket: tuple[str, ...]
    period: str
    requested_source: str
    retrieved_at: str
    rows: tuple[Mag11TrendRow, ...]


def build_mag11_trend_snapshot(
    provider: MarketDataProvider,
    *,
    basket: tuple[str, ...],
    period: str,
    requested_source: str,
    now: datetime | None = None,
) -> Mag11TrendSnapshot:
    """Build a read-only daily snapshot; options gamma is deliberately out of scope."""
    if len(basket) != 11 or len(set(basket)) != 11:
        raise ValueError("MAG11 trend snapshots require exactly 11 distinct symbols")
    retrieved_at = now or datetime.now(timezone.utc)
    if retrieved_at.utcoffset() is None:
        raise ValueError("MAG11 snapshot clock requires an aware timestamp")
    rows = tuple(_trend_row(provider, symbol=symbol, period=period) for symbol in basket)
    return Mag11TrendSnapshot(
        schema_version=SCHEMA_VERSION,
        basket=basket,
        period=period,
        requested_source=requested_source.strip().lower(),
        retrieved_at=retrieved_at.isoformat(),
        rows=rows,
    )


def save_mag11_trend_snapshot(snapshot: Mag11TrendSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(snapshot)
    path.write_text(json.dumps(payload, sort_keys=True, allow_nan=False), encoding="utf-8")


def load_mag11_trend_snapshot(path: Path) -> Mag11TrendSnapshot:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported MAG11 snapshot")
    basket = value.get("basket")
    rows = value.get("rows")
    if (
        not isinstance(basket, list)
        or len(basket) != 11
        or len(set(basket)) != 11
        or not all(isinstance(symbol, str) and symbol for symbol in basket)
        or not isinstance(rows, list)
        or len(rows) != 11
        or not isinstance(value.get("period"), str)
        or not isinstance(value.get("requested_source"), str)
        or not isinstance(value.get("retrieved_at"), str)
    ):
        raise ValueError("Invalid MAG11 snapshot")
    parsed_rows: list[Mag11TrendRow] = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("Invalid MAG11 trend row")
        parsed_rows.append(
            Mag11TrendRow(
                symbol=_required_string(item, "symbol"),
                close=_optional_number(item, "close"),
                return_1d=_optional_number(item, "return_1d"),
                return_5d=_optional_number(item, "return_5d"),
                actual_source=_required_string(item, "actual_source"),
                fallback_used=_optional_bool(item, "fallback_used"),
                retrieved_at=_optional_string(item, "retrieved_at"),
                last_bar_label=_optional_string(item, "last_bar_label"),
                state=_required_string(item, "state"),
            )
        )
    return Mag11TrendSnapshot(
        schema_version=SCHEMA_VERSION,
        basket=tuple(cast(list[str], basket)),
        period=value["period"],
        requested_source=value["requested_source"].lower(),
        retrieved_at=value["retrieved_at"],
        rows=tuple(parsed_rows),
    )


def _trend_row(provider: MarketDataProvider, *, symbol: str, period: str) -> Mag11TrendRow:
    try:
        bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
        if len(bars) < 6 or "close" not in bars:
            raise ValueError("Insufficient daily history")
        closes = pd.to_numeric(bars["close"], errors="coerce")
        current, prior_1d, prior_5d = closes.iloc[-1], closes.iloc[-2], closes.iloc[-6]
        if not all(math.isfinite(float(value)) and float(value) > 0 for value in (current, prior_1d, prior_5d)):
            raise ValueError("Invalid daily close")
        provenance = bars.attrs.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
        return Mag11TrendRow(
            symbol=symbol,
            close=round(float(current), 2),
            return_1d=round((float(current) / float(prior_1d)) - 1.0, 6),
            return_5d=round((float(current) / float(prior_5d)) - 1.0, 6),
            actual_source=str(provenance.get("actual_source") or "unknown"),
            fallback_used=provenance.get("fallback_used") if type(provenance.get("fallback_used")) is bool else None,
            retrieved_at=provenance.get("retrieved_at") if isinstance(provenance.get("retrieved_at"), str) else None,
            last_bar_label=provenance.get("last_bar_label") if isinstance(provenance.get("last_bar_label"), str) else None,
            state="available",
        )
    except Exception:
        return Mag11TrendRow(
            symbol=symbol, close=None, return_1d=None, return_5d=None,
            actual_source="unavailable", fallback_used=None, retrieved_at=None,
            last_bar_label=None, state="unavailable",
        )


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError("Invalid MAG11 trend row")
    return item


def _optional_string(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError("Invalid MAG11 trend row")
    return item


def _optional_bool(value: dict[str, Any], key: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if type(item) is not bool:
        raise ValueError("Invalid MAG11 trend row")
    return item


def _optional_number(value: dict[str, Any], key: str) -> float | None:
    item = value.get(key)
    if item is None:
        return None
    if type(item) not in {int, float} or not math.isfinite(float(item)):
        raise ValueError("Invalid MAG11 trend row")
    return float(item)
