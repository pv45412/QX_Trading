"""Abstract base class for market data provider abstractions."""

from abc import ABC, abstractmethod
from typing import Any
import pandas as pd

from qx.core.models.freshness import DataFreshness


class MarketDataProvider(ABC):
    """Domain boundary interface for external market data sources."""

    @abstractmethod
    def get_quote(self, symbol: str) -> DataFreshness[dict[str, Any]]:
        """Fetch latest quote snapshot for symbol."""
        pass

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int = 100,
    ) -> DataFreshness[pd.DataFrame]:
        """Fetch historical OHLCV bar data for symbol."""
        pass

    @abstractmethod
    def get_option_chain(
        self,
        symbol: str,
        expiration: str | None = None,
    ) -> DataFreshness[dict[str, Any]]:
        """Fetch option chain for symbol."""
        pass

    @abstractmethod
    def get_greeks(
        self,
        symbol: str,
        option_symbol: str,
    ) -> DataFreshness[dict[str, float]]:
        """Fetch greeks (delta, gamma, theta, vega, iv) for option symbol."""
        pass
