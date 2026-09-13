from dataclasses import dataclass
from pathlib import Path

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.core.engine import ScannerEngine
from qx.data.cache import CachedMarketDataProvider
from qx.data.metadata import SymbolMetadataStore
from qx.data.providers import MarketDataProvider
from qx.data.universe import UNIVERSE_OPTIONS, UniverseLoader
from qx.market.sector_rotation import SECTOR_ETFS
from qx.market.spx_dashboard import FUTURES_MARKETS
from qx.models.scan import ScanRunResult
from qx.patterns.profiles import build_rectangle_parameters
from qx.processing.data_pipeline import CacheRefreshResult, refresh_bar_cache
from qx.reports.daily_workflow import DailyWorkflowReport, build_daily_workflow_report
from qx.storage.feature_cache import SQLiteFeatureCache
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.workflow import SQLiteWorkflowRepository


@dataclass(frozen=True)
class OvernightWorkflowResult:
    cache_refresh: CacheRefreshResult
    scan_result: ScanRunResult
    scan_run_id: int
    workflow_run_id: int
    workflow_report: DailyWorkflowReport
    metadata_symbols: int
    auth_warning: str = ""


def run_overnight_workflow(
    *,
    provider: MarketDataProvider,
    universe: str = "sp500",
    period: str = "2y",
    profile: str = "Classic rectangle",
    lookback: int = 40,
    max_range_pct: float = 0.25,
    refresh: bool = False,
    database: Path = Path("data/scanner_history.db"),
    token_manager: SchwabTokenManager | None = None,
) -> OvernightWorkflowResult:
    auth_warning = _auth_warning(token_manager)
    symbols = _symbols_for_refresh(universe)
    metadata_symbols = SymbolMetadataStore().refresh_sp500()
    cache_refresh = refresh_bar_cache(symbols, provider, period=period, refresh=refresh)

    cached_provider = CachedMarketDataProvider(provider, refresh=False)
    scan_result = ScannerEngine(
        provider=cached_provider,
        parameters=build_rectangle_parameters(
            profile,
            lookback=lookback,
            max_range_pct=max_range_pct,
        ),
        feature_cache=SQLiteFeatureCache(),
    ).scan_symbols(_symbols_for_scan(universe), period=period)

    scan_repository = SQLiteScanRepository(database)
    scan_run_id = scan_repository.save_scan_run(scan_result)
    workflow_report = build_daily_workflow_report(
        provider=cached_provider,
        repository=scan_repository,
        period=period,
    )
    workflow_run_id = SQLiteWorkflowRepository(database).save(workflow_report)
    return OvernightWorkflowResult(
        cache_refresh=cache_refresh,
        scan_result=scan_result,
        scan_run_id=scan_run_id,
        workflow_run_id=workflow_run_id,
        workflow_report=workflow_report,
        metadata_symbols=metadata_symbols,
        auth_warning=auth_warning,
    )


def _auth_warning(token_manager: SchwabTokenManager | None) -> str:
    if token_manager is None:
        return ""
    status = token_manager.status()
    if status.restart_required:
        return status.message
    if not status.access_token_valid:
        try:
            token_manager.get_access_token()
        except Exception as exc:
            return f"Schwab token refresh failed: {exc}"
    return ""


def _symbols_for_refresh(universe: str) -> list[str]:
    futures_symbols = [symbol for symbol, _, _ in FUTURES_MARKETS]
    market_symbols = ["SPY", "QQQ", "IWM", "^VIX", *futures_symbols, *SECTOR_ETFS.values()]
    return sorted(set([*_symbols_for_scan(universe), *market_symbols]))


def _symbols_for_scan(universe: str) -> list[str]:
    loader = UniverseLoader()
    if universe.strip().lower() == "all":
        symbols: list[str] = []
        for universe_id in UNIVERSE_OPTIONS.values():
            symbols.extend(loader.load(universe_id))
        return sorted(set(symbols))
    return loader.load(universe)
