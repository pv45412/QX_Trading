from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    provider: str
    last: float | None = None
    change_pct: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    timestamp: datetime | None = None
    resolved_symbol: str | None = None
    asset_type: str | None = None
    realtime: bool | None = None
    expiration: datetime | None = None
    trade_timestamp: datetime | None = None


class QuoteProvider(Protocol):
    def get_quote(self, symbol: str) -> QuoteSnapshot:
        """Return a current or delayed quote snapshot for a symbol."""


class YFinanceQuoteProvider:
    provider_name = "yfinance"

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        import yfinance as yf  # type: ignore[import-untyped]

        ticker = yf.Ticker(symbol)
        fast_info = ticker.fast_info
        last = _safe_float(_fast_info_value(fast_info, "last_price"))
        previous_close = _safe_float(_fast_info_value(fast_info, "previous_close"))
        volume = _safe_float(_fast_info_value(fast_info, "last_volume"))
        change_pct = _change_pct(last, previous_close)
        return QuoteSnapshot(
            symbol=symbol.upper(),
            provider=self.provider_name,
            last=last,
            change_pct=change_pct,
            volume=volume,
        )


def _fast_info_value(fast_info: Any, key: str) -> Any:
    try:
        return fast_info[key]
    except Exception:
        return getattr(fast_info, key, None)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _change_pct(last: float | None, previous_close: float | None) -> float | None:
    if last is None or previous_close is None or previous_close <= 0:
        return None
    return (last / previous_close) - 1.0
