import pandas as pd
from qx.data.provenance import tag_bars

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.brokers.schwab.options import SchwabOptionsChainProvider
from qx.brokers.schwab.accounts import SchwabReadOnlyAccountSnapshotProvider
from qx.brokers.schwab.quotes import SchwabQuoteProvider
from qx.brokers.schwab.timing import SchwabEmaTimingProvider
from qx.config.settings import Settings, get_settings
from qx.data.metadata import SymbolMetadataStore
from qx.data.providers import MarketDataProvider, YFinanceMarketDataProvider
from qx.data.fundamentals import (
    CachedFundamentalProvider,
    EmptyFundamentalProvider,
    FundamentalProvider,
    YFinanceFundamentalProvider,
)
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.options.chains import OptionsChainProvider, YFinanceOptionsChainProvider
from qx.options.timing import EmaTimingProvider, YFinanceEmaTimingProvider
from qx.data.quotes import QuoteProvider, YFinanceQuoteProvider, QuoteSnapshot
from qx.pipeline.providers import (
    CanonicalAccountSnapshotProvider,
    CanonicalOptionChainSnapshotProvider,
    SchwabCanonicalOptionChainSnapshotProvider,
)


def build_market_data_provider(
    provider_name: str | None = None,
    *,
    settings: Settings | None = None,
) -> MarketDataProvider:
    resolved_settings = settings or get_settings()
    name = (provider_name or resolved_settings.data_provider).strip().lower()
    if name == "schwab":
        return SchwabMarketDataProvider(_schwab_client(settings))
    if name == "yfinance":
        return YFinanceMarketDataProvider()
    raise ValueError(f"Unknown market data provider: {provider_name or resolved_settings.data_provider}")


def build_fallback_market_data_provider(
    primary_name: str,
    *,
    settings: Settings | None = None,
) -> MarketDataProvider:
    primary = build_market_data_provider(primary_name, settings=settings)
    if primary_name.strip().lower() == "yfinance":
        return primary
    return FallbackMarketDataProvider(primary, YFinanceMarketDataProvider())


def build_quote_provider(
    provider_name: str,
    *,
    settings: Settings | None = None,
) -> QuoteProvider:
    name = provider_name.strip().lower()
    if name == "schwab":
        return FallbackQuoteProvider(
            SchwabQuoteProvider(_schwab_client(settings)),
            YFinanceQuoteProvider(),
        )
    if name == "yfinance":
        return YFinanceQuoteProvider()
    raise ValueError(f"Unknown quote provider: {provider_name}")


def build_options_chain_provider(
    provider_name: str,
    *,
    settings: Settings | None = None,
    min_days_to_expiration: int = 30,
    max_days_to_expiration: int = 180,
    strike_count: int = 30,
) -> OptionsChainProvider | None:
    name = provider_name.strip().lower()
    if name == "none":
        return None
    if name == "schwab":
        return SchwabOptionsChainProvider(
            _schwab_client(settings),
            min_days_to_expiration=min_days_to_expiration,
            max_days_to_expiration=max_days_to_expiration,
            strike_count=strike_count,
        )
    if name == "yfinance":
        return YFinanceOptionsChainProvider()
    raise ValueError(f"Unknown options chain provider: {provider_name}")


def build_canonical_option_snapshot_provider(
    provider_name: str | None = None,
    *,
    settings: Settings | None = None,
) -> CanonicalOptionChainSnapshotProvider | None:
    resolved_settings = settings or get_settings()
    name = (provider_name or resolved_settings.data_provider).strip().lower()
    if name == "none":
        return None
    if name == "schwab":
        return SchwabCanonicalOptionChainSnapshotProvider(_schwab_client(settings))
    raise ValueError(f"Unsupported canonical option provider: {name}")


def build_canonical_account_snapshot_provider(
    provider_name: str | None = None,
    *,
    settings: Settings | None = None,
    metadata_store: SymbolMetadataStore | None = None,
) -> CanonicalAccountSnapshotProvider | None:
    resolved_settings = settings or get_settings()
    name = (provider_name or resolved_settings.data_provider).strip().lower()
    if name == "none":
        return None
    if name == "schwab":
        return SchwabReadOnlyAccountSnapshotProvider(
            _schwab_client(settings), metadata_store=metadata_store
        )
    raise ValueError(f"Unsupported canonical account provider: {name}")


def build_fundamental_provider(provider_name: str, *, refresh: bool = False) -> FundamentalProvider:
    name = provider_name.strip().lower()
    if name == "none":
        return EmptyFundamentalProvider()
    if name in {"yfinance", "schwab"}:
        return CachedFundamentalProvider(YFinanceFundamentalProvider(), refresh=refresh)
    raise ValueError(f"Unknown fundamental provider: {provider_name}")


def build_ema_timing_provider(provider_name: str) -> EmaTimingProvider | None:
    name = provider_name.strip().lower()
    if name == "none":
        return None
    if name == "yfinance":
        return YFinanceEmaTimingProvider()
    if name == "schwab":
        return SchwabEmaTimingProvider(_schwab_client())
    raise ValueError(f"Unknown EMA timing provider: {provider_name}")


def _schwab_client(settings: Settings | None = None) -> SchwabApiClient:
    resolved_settings = settings or get_settings()
    token_manager = SchwabTokenManager(settings if settings is not None else get_settings)
    return SchwabApiClient(token_manager, base_url=resolved_settings.schwab_api_base_url)


class FallbackMarketDataProvider:
    def __init__(
        self,
        primary: MarketDataProvider,
        fallback: MarketDataProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        try:
            bars = self.primary.get_daily_bars(request)
        except Exception:
            return tag_bars(self.fallback.get_daily_bars(request), self.fallback, fallback_used=True)
        return tag_bars(bars, self.primary)

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        try:
            bars = self.primary.get_intraday_bars(request)
        except Exception:
            return tag_bars(self.fallback.get_intraday_bars(request), self.fallback, fallback_used=True)
        return tag_bars(bars, self.primary)


class FallbackQuoteProvider:
    def __init__(self, primary: QuoteProvider, fallback: QuoteProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        try:
            return self.primary.get_quote(symbol)
        except Exception:
            return self.fallback.get_quote(symbol)
