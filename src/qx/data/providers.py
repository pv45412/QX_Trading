from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Protocol

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from qx.models.market import BarDataRequest, IntradayBarDataRequest

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


class MarketDataProvider(Protocol):
    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        """Return daily OHLCV bars indexed by date."""

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        """Return intraday OHLCV bars indexed by timestamp."""


class CsvMarketDataProvider:
    """Loads daily OHLCV data from CSV files for repeatable local scans."""

    provider_name = "csv"

    def __init__(self, root: Path) -> None:
        self.root = root

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        path = self.root / f"{request.symbol.upper()}.csv"
        if not path.exists():
            raise FileNotFoundError(f"CSV data not found for {request.symbol}: {path}")
        return normalize_ohlcv(pd.read_csv(path))

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        raise NotImplementedError("CSV intraday bars are not configured")


class YFinanceMarketDataProvider:
    """Downloads daily OHLCV data from Yahoo Finance through yfinance."""

    provider_name = "yfinance"

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            frame = yf.download(
                request.symbol,
                start=request.start,
                end=request.end,
                period=None if request.start else request.period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        if frame.empty:
            raise ValueError(f"No price data returned by yfinance for {request.symbol}")
        return normalize_ohlcv(frame)

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        interval = f"{request.interval_minutes}m"
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            frame = yf.download(
                request.symbol,
                period=request.period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                prepost=request.include_extended_hours,
                threads=False,
            )
        if frame.empty:
            raise ValueError(f"No {interval} price data returned by yfinance for {request.symbol}")
        return normalize_ohlcv(frame)


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("Market data frame is empty")

    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = [str(col[0]).lower() for col in normalized.columns]
    else:
        normalized.columns = [str(col).strip().lower().replace(" ", "_") for col in normalized.columns]

    rename_map = {
        "adj_close": "adjusted_close",
    }
    normalized = normalized.rename(columns=rename_map)

    missing = [column for column in REQUIRED_COLUMNS if column not in normalized.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(missing)}")

    normalized = normalized[REQUIRED_COLUMNS].dropna()
    normalized["volume"] = normalized["volume"].astype(float)
    return normalized.sort_index()
