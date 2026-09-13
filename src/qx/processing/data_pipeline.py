from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from qx.data.cache import CachedMarketDataProvider
from qx.data.providers import MarketDataProvider
from qx.models.market import BarDataRequest


@dataclass(frozen=True)
class CacheRefreshFailure:
    symbol: str
    message: str


@dataclass(frozen=True)
class CacheRefreshResult:
    total_symbols: int
    refreshed_symbols: int
    failed_symbols: int
    failures: list[CacheRefreshFailure] = field(default_factory=list)


def refresh_bar_cache(
    symbols: Iterable[str],
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    refresh: bool = False,
    max_workers: int = 12,
) -> CacheRefreshResult:
    """Load symbols through the cache provider so later scans run from disk."""

    normalized_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    cached_provider = CachedMarketDataProvider(provider, refresh=refresh)
    failures: list[CacheRefreshFailure] = []
    refreshed = 0

    def load_symbol(symbol: str) -> str:
        cached_provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
        return symbol

    workers = max(1, min(max_workers, len(normalized_symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_by_symbol = {executor.submit(load_symbol, symbol): symbol for symbol in normalized_symbols}
        for future in as_completed(future_by_symbol):
            symbol = future_by_symbol[future]
            try:
                future.result()
                refreshed += 1
            except Exception as exc:
                failures.append(CacheRefreshFailure(symbol=symbol, message=str(exc)))

    failures.sort(key=lambda failure: failure.symbol)

    return CacheRefreshResult(
        total_symbols=len(normalized_symbols),
        refreshed_symbols=refreshed,
        failed_symbols=len(failures),
        failures=failures,
    )
