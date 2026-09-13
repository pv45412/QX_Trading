from __future__ import annotations

from typing import Any

import pandas as pd

from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.market_data import _candles_frame as _market_candles_frame
from qx.options.timing import EmaTimingSnapshot, build_ema_timing_snapshot


class SchwabEmaTimingProvider:
    """Builds daily/hourly/30m/15m EMA timing from Schwab price history."""

    def __init__(self, client: SchwabApiClient) -> None:
        self.client = client

    def get_timing(self, symbol: str) -> EmaTimingSnapshot:
        daily = self._price_history(
            symbol,
            period_type="month",
            period=3,
            frequency_type="daily",
            frequency=1,
        )
        thirty = self._price_history(
            symbol,
            period_type="day",
            period=10,
            frequency_type="minute",
            frequency=30,
        )
        fifteen = self._price_history(
            symbol,
            period_type="day",
            period=5,
            frequency_type="minute",
            frequency=15,
        )
        hourly = _resample_ohlcv(thirty, "60min")
        return build_ema_timing_snapshot(
            daily=daily,
            hourly=hourly,
            thirty_min=thirty,
            fifteen_min=fifteen,
        )

    def _price_history(
        self,
        symbol: str,
        *,
        period_type: str,
        period: int,
        frequency_type: str,
        frequency: int,
    ) -> pd.DataFrame:
        payload = self.client.get(
            "/marketdata/v1/pricehistory",
            params={
                "symbol": symbol,
                "periodType": period_type,
                "period": period,
                "frequencyType": frequency_type,
                "frequency": frequency,
                "needExtendedHoursData": "false",
                "needPreviousClose": "false",
            },
        )
        candles = payload.get("candles", [])
        if not isinstance(candles, list) or not candles:
            raise ValueError(f"No Schwab {frequency_type} timing data returned for {symbol}")
        return _candles_frame(candles, daily=frequency_type == "daily")


def _candles_frame(candles: list[Any], *, daily: bool = False) -> pd.DataFrame:
    return _market_candles_frame(candles, daily=daily).astype(float)


def _resample_ohlcv(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    resampled = frame.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return resampled.dropna(subset=["open", "high", "low", "close"])
