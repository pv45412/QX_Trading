"""Fund-reported top holdings, separate from curated scanner candidates."""

from datetime import datetime, timezone
from functools import lru_cache
import math
from typing import Any
from pathlib import Path
import json
import re

from qx.data.cache import _atomic_write

import yfinance as yf  # type: ignore[import-untyped]


@lru_cache(maxsize=58)
def top_holdings(symbol: str, hour_bucket: int) -> dict[str, Any]:
    """Bounded hourly cache. Retrieval time is not the fund's holdings date."""
    return _fetch_top_holdings(symbol)


def _fetch_top_holdings(symbol: str) -> dict[str, Any]:
    frame = yf.Ticker(symbol).funds_data.top_holdings
    rows: list[dict[str, Any]] = []
    for ticker, row in frame.iterrows():
        weight = float(row["Holding Percent"])
        if not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("Invalid holding weight")
        rows.append({"symbol": str(ticker), "name": str(row["Name"]), "weight": weight})
    if not rows:
        raise ValueError("Holdings unavailable")
    rows.sort(key=lambda row: float(row["weight"]), reverse=True)
    return {"symbol": symbol, "source": "Yahoo Finance fund data", "holdings_as_of": None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "rows": rows[:10]}


def _holdings_path(symbol: str, cache_dir: Path) -> Path:
    if not re.fullmatch(r"[A-Z]{1,10}", symbol):
        raise ValueError("Invalid fund symbol")
    return cache_dir / f"{symbol}.json"


def _validate_holdings(payload: Any, symbol: str) -> None:
    """Use the same identity and concentration checks for saved and provider data."""
    if (not isinstance(payload, dict) or payload.get("symbol") != symbol
            or not isinstance(payload.get("rows"), list) or not payload["rows"]
            or not isinstance(payload.get("source"), str) or not payload["source"].strip()):
        raise ValueError("Invalid fund holdings")
    try:
        retrieved = datetime.fromisoformat(payload["retrieved_at"])
        if retrieved.utcoffset() is None or retrieved > datetime.now(timezone.utc):
            raise ValueError("Invalid holdings timestamp")
        if payload.get("holdings_as_of") is not None:
            datetime.fromisoformat(payload["holdings_as_of"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid holdings timestamp") from None
    seen = set()
    total = 0.0
    for row in payload["rows"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid holding")
        ticker, weight = row.get("symbol"), row.get("weight")
        if (not isinstance(ticker, str) or not ticker.strip() or ticker.strip().upper() in seen
                or not isinstance(weight, (int, float)) or isinstance(weight, bool) or not math.isfinite(weight)
                or not 0 <= weight <= 1
                or (row.get("name") is not None and not isinstance(row["name"], str))):
            raise ValueError("Invalid holding")
        seen.add(ticker.strip().upper())
        total += weight
    if total > 1.001:
        raise ValueError("Invalid holdings concentration")


def saved_top_holdings(symbol: str, cache_dir: Path) -> dict[str, Any]:
    """Read compatible saved holdings only; never fetch, write, or redate them."""
    payload = json.loads(_holdings_path(symbol, cache_dir).read_text(encoding="utf-8"))
    _validate_holdings(payload, symbol)
    return {**payload, "stale_holdings": True, "holdings_status": "SAVED_UNVERIFIED",
            "refresh_error": None}


def cached_top_holdings(
    symbol: str, hour_bucket: int, cache_dir: Path, *, force_refresh: bool = False,
) -> dict[str, Any]:
    """Explicit refresh only. Retain compatible saved data on provider failure."""
    path = _holdings_path(symbol, cache_dir)
    try:
        result = _fetch_top_holdings(symbol) if force_refresh else top_holdings(symbol, hour_bucket)
        _validate_holdings(result, symbol)
    except Exception:
        cached = saved_top_holdings(symbol, cache_dir)
        return {**cached, "refresh_error": "Holdings refresh failed. Showing saved holdings; weights may have changed."}
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(result, allow_nan=False).encode())
    except OSError:
        # Persistence failure must not hide a successful read-only provider response.
        return {**result, "stale_holdings": False, "holdings_status": "REFRESHED_UNSAVED",
                "cache_warning": "Holdings could not be saved locally"}
    return {**result, "stale_holdings": False, "holdings_status": "REFRESHED"}
