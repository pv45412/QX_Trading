import pandas as pd

from qx.data.factory import (
    FallbackMarketDataProvider,
    build_ema_timing_provider,
    build_fallback_market_data_provider,
    build_fundamental_provider,
    build_market_data_provider,
    build_options_chain_provider,
)
from qx.data.fundamentals import CachedFundamentalProvider, EmptyFundamentalProvider, YFinanceFundamentalProvider
from qx.data.providers import YFinanceMarketDataProvider
from qx.models.market import BarDataRequest
from qx.options.chains import YFinanceOptionsChainProvider
from qx.options.timing import YFinanceEmaTimingProvider
from qx.brokers.schwab.timing import SchwabEmaTimingProvider
from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.config.settings import Settings


class FailingProvider:
    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        raise ValueError("primary failed")


class WorkingProvider:
    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2026-01-01", periods=1))


def test_factory_builds_yfinance_market_data_when_requested() -> None:
    provider = build_market_data_provider("yfinance")

    assert isinstance(provider, YFinanceMarketDataProvider)


def test_factory_defaults_to_schwab_market_data() -> None:
    provider = build_market_data_provider(settings=Settings(data_provider="schwab"))

    assert isinstance(provider, SchwabMarketDataProvider)


def test_factory_rejects_unknown_market_data_provider() -> None:
    try:
        build_market_data_provider("bad-provider")
    except ValueError as exc:
        assert "Unknown market data provider" in str(exc)
    else:
        raise AssertionError("Expected unknown market data provider to raise")


def test_fallback_factory_wraps_schwab_with_yfinance_fallback() -> None:
    provider = build_fallback_market_data_provider("schwab", settings=Settings(data_provider="schwab"))

    assert isinstance(provider, FallbackMarketDataProvider)
    assert isinstance(provider.primary, SchwabMarketDataProvider)
    assert isinstance(provider.fallback, YFinanceMarketDataProvider)


def test_fallback_factory_does_not_wrap_yfinance() -> None:
    provider = build_fallback_market_data_provider("yfinance")

    assert isinstance(provider, YFinanceMarketDataProvider)


def test_factory_builds_yfinance_or_no_options_provider() -> None:
    assert build_options_chain_provider("none") is None
    assert isinstance(build_options_chain_provider("yfinance"), YFinanceOptionsChainProvider)


def test_factory_builds_fundamental_and_timing_providers() -> None:
    assert isinstance(build_fundamental_provider("none"), EmptyFundamentalProvider)
    cached = build_fundamental_provider("yfinance")
    assert isinstance(cached, CachedFundamentalProvider)
    assert isinstance(cached.provider, YFinanceFundamentalProvider)
    schwab_cached = build_fundamental_provider("schwab")
    assert isinstance(schwab_cached, CachedFundamentalProvider)
    assert isinstance(schwab_cached.provider, YFinanceFundamentalProvider)
    assert build_ema_timing_provider("none") is None
    assert isinstance(build_ema_timing_provider("yfinance"), YFinanceEmaTimingProvider)
    assert isinstance(build_ema_timing_provider("schwab"), SchwabEmaTimingProvider)


def test_fallback_market_data_provider_uses_fallback() -> None:
    provider = FallbackMarketDataProvider(FailingProvider(), WorkingProvider())

    assert provider.get_daily_bars(BarDataRequest(symbol="SPY"))["close"].iloc[0] == 1.0
