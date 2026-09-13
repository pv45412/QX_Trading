from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any

from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.symbols import schwab_market_data_symbol
from qx.data.quotes import QuoteSnapshot


class SchwabQuoteProvider:
    provider_name = "schwab"

    def __init__(self, client: SchwabApiClient) -> None:
        self.client = client

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        request_symbol = _schwab_quote_symbol(symbol)
        payload = self.client.get("/marketdata/v1/quotes", params={"symbols": request_symbol})
        quote_payload = _extract_symbol_payload(payload, request_symbol)
        quote = _as_dict(quote_payload.get("quote")) or quote_payload
        regular = _as_dict(quote_payload.get("regular"))
        reference = _as_dict(quote_payload.get("reference"))
        return QuoteSnapshot(
            symbol=symbol.upper(),
            provider=self.provider_name,
            last=_first_float(quote, regular, keys=["lastPrice", "last", "mark", "markPrice"]),
            change_pct=_first_pct(quote, regular),
            bid=_first_float(quote, regular, keys=["bidPrice", "bid"]),
            ask=_first_float(quote, regular, keys=["askPrice", "ask"]),
            volume=_first_float(quote, regular, keys=["totalVolume", "volume"]),
            timestamp=_first_timestamp(quote, regular),
            resolved_symbol=quote_payload["symbol"],
            asset_type=quote_payload.get("assetMainType"),
            realtime=quote_payload.get("realtime") if type(quote_payload.get("realtime")) is bool else None,
            expiration=_first_timestamp({"quoteTime": reference.get("futureExpirationDate")}),
            trade_timestamp=_first_timestamp({key: quote[key] for key in ("tradeTime", "tradeTimeInLong") if key in quote}),
        )


def _schwab_quote_symbol(symbol: str) -> str:
    return schwab_market_data_symbol(symbol)


def _extract_symbol_payload(payload: dict[str, Any], symbol: str) -> dict[str, Any]:
    candidates = []
    for key, item in payload.items():
        if not isinstance(item, dict) or not _matches_symbol(symbol, key):
            continue
        resolved = item.get("symbol", key)
        if (not isinstance(resolved, str) or not _matches_symbol(symbol, resolved)
                or (key != symbol and resolved != key)):
            raise ValueError("Schwab quote identity mismatch")
        candidates.append({**item, "symbol": resolved})
    if len(candidates) != 1:
        raise ValueError("Schwab quote identity unavailable or ambiguous")
    return candidates[0]


def _matches_symbol(requested: str, returned: str) -> bool:
    if requested == returned:
        return True
    return bool(re.fullmatch(r"/[A-Z]{1,6}", requested)
                and re.fullmatch(re.escape(requested) + r"[FGHJKMNQUVXZ](?:\d{2}|\d{4})", returned))


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first_float(*sections: dict[str, Any], keys: list[str]) -> float | None:
    for section in sections:
        for key in keys:
            value = section.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                number = float(value)
                if math.isfinite(number):
                    return number
            except (TypeError, ValueError):
                continue
    return None


def _first_pct(*sections: dict[str, Any]) -> float | None:
    value = _first_float(
        *sections,
        keys=[
            "netPercentChange",
            "netChangePercent",
            "regularMarketPercentChange",
            "markPercentChange",
        ],
    )
    if value is None:
        return None
    return value / 100


def _first_timestamp(*sections: dict[str, Any]) -> datetime | None:
    value = _first_float(
        *sections,
        keys=[
            "quoteTimeInLong",
            "quoteTime",
            "tradeTime",
            "tradeTimeInLong",
            "regularMarketTradeTimeInLong",
            "lastPriceTime",
        ],
    )
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    timestamp = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
