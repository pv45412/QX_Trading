"""Ranked Schwab mover subsets, never index membership or breadth."""
from datetime import datetime, timezone
import math
from typing import Any

from qx.brokers.schwab.client import SchwabApiClient


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid numeric value")
    return float(value)


def normalize_screeners(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("screeners")
    if not isinstance(items, list) or len(items) > 10:
        raise ValueError("Unexpected movers response")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid screener")
        symbol = item.get("symbol")
        last, change = _number(item.get("lastPrice")), _number(item.get("netChange"))
        if not isinstance(symbol, str) or not symbol.strip() or symbol in seen:
            raise ValueError("Invalid mover identity or price")
        reference = last - change
        if last <= 0 or not math.isfinite(reference) or reference <= 0:
            raise ValueError("Invalid reference price")
        daily = change / reference
        if not math.isfinite(daily):
            raise ValueError("Invalid return")
        seen.add(symbol)
        result.append({"symbol": symbol, "last": last, "change": change,
                       "return": daily})
    return result


def fetch_top_movers(client: SchwabApiClient) -> dict[str, Any]:
    groups = {}
    for key, sort in (("highest", "PERCENT_CHANGE_UP"), ("lowest", "PERCENT_CHANGE_DOWN")):
        payload = client.get("/marketdata/v1/movers/$SPX", params={"sort": sort, "frequency": 0})
        rows = normalize_screeners(payload)
        groups[key] = sorted(rows, key=lambda row: row["return"], reverse=key == "highest")
    return {"groups": groups, "source": "schwab", "index": "$SPX",
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "market_as_of": None,
            "scope": "Ranked subsets only; not full-index breadth or membership"}
