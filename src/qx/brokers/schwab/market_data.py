from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.symbols import schwab_market_data_symbol
from qx.data.providers import normalize_ohlcv
from qx.models.market import BarDataRequest, IntradayBarDataRequest


class SchwabMarketDataProvider:
    """Market data provider backed by Schwab price history endpoints."""

    provider_name = "schwab"

    def __init__(self, client: SchwabApiClient) -> None:
        self.client = client

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        payload = self.client.get(
            "/marketdata/v1/pricehistory",
            params={
                "symbol": schwab_market_data_symbol(request.symbol),
                "periodType": "year",
                "period": _period_years(request.period),
                "frequencyType": "daily",
                "frequency": 1,
                "needExtendedHoursData": "false",
                "needPreviousClose": "false",
            },
        )
        candles = payload.get("candles", [])
        if not isinstance(candles, list) or not candles:
            raise ValueError(f"No Schwab price history returned for {request.symbol}")
        return normalize_ohlcv(_candles_frame(candles, daily=True))

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        payload = self.client.get(
            "/marketdata/v1/pricehistory",
            params={
                "symbol": schwab_market_data_symbol(request.symbol),
                "periodType": "day",
                "period": _intraday_period_days(request.period),
                "frequencyType": "minute",
                "frequency": request.interval_minutes,
                "needExtendedHoursData": "true" if request.include_extended_hours else "false",
                "needPreviousClose": "false",
            },
        )
        candles = payload.get("candles", [])
        if not isinstance(candles, list) or not candles:
            raise ValueError(
                f"No Schwab {request.interval_minutes}m price history returned for {request.symbol}"
            )
        return normalize_ohlcv(_candles_frame(candles))


def _period_years(period: str) -> int:
    if period.endswith("y"):
        return max(int(period[:-1]), 1)
    if period in {"6mo", "1mo", "3mo"}:
        return 1
    return 2


def _intraday_period_days(period: str) -> int:
    normalized = period.strip().lower()
    if normalized.endswith("d"):
        return max(min(int(normalized[:-1]), 10), 1)
    if normalized in {"1mo", "3mo", "6mo", "1y", "2y"}:
        return 10
    return 5


def _candles_frame(candles: list[Any], *, daily: bool = False) -> pd.DataFrame:
    """Decode epoch instants; daily bars use ET calendar labels, not quote times."""
    rows: list[dict[str, object]] = []
    for candle in candles:
        if not isinstance(candle, dict):
            raise ValueError("Invalid Schwab candle record")
        timestamp_ms = candle.get("datetime")
        if (not isinstance(timestamp_ms, (int, float)) or isinstance(timestamp_ms, bool)
                or not 0 < timestamp_ms <= 253_402_300_799_999
                or int(timestamp_ms) != timestamp_ms):
            raise ValueError("Invalid Schwab candle timestamp")
        try:
            instant = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("Invalid Schwab candle timestamp") from exc
        rows.append(
            {
                "date": instant,
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
                "volume": candle.get("volume"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("Schwab candle response had no usable rows")
    frame = frame.set_index("date")
    index = pd.DatetimeIndex(frame.index)
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Schwab candle timestamps must be unique and ordered")
    if daily:
        # Derive the session label before dropping timezone information. Never use host time.
        index = index.tz_convert("America/New_York").normalize().tz_localize(None)
        if not index.is_unique:
            raise ValueError("Multiple Schwab daily candles map to the same ET date")
    frame.index = index
    return frame
