from pathlib import Path

import pandas as pd
import pytest

from qx.models.market import BarDataRequest
from qx.core.engine import ScannerEngine
from qx.data.metadata import SymbolMetadata, SymbolMetadataStore
from qx.storage.sqlite import SQLiteScanRepository
from qx.watchlist.engine import (
    _read_failure_cache,
    _write_failure_cache,
    build_broad_watchlist,
    watchlist_frame,
)
from tests.unit.test_overnight_workflow import StaticProvider, _frames


@pytest.fixture(autouse=True)
def _isolate_watchlist_failure_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qx.watchlist.engine.WATCHLIST_FAILURE_CACHE", tmp_path / "watchlist_failures.csv")


class StaticMetadata(SymbolMetadataStore):
    def get(self, symbol: str) -> SymbolMetadata:
        return SymbolMetadata(
            symbol=symbol,
            name=f"{symbol} Inc",
            sector="Information Technology",
            industry="Software",
        )


class EnrichingMetadata(SymbolMetadataStore):
    def __init__(self) -> None:
        super().__init__(Path("unused.csv"))
        self.enriched = False

    def get(self, symbol: str) -> SymbolMetadata:
        if self.enriched:
            return SymbolMetadata(
                symbol=symbol,
                name=f"{symbol} Enriched",
                sector="Industrials",
                industry="Engineering",
            )
        return SymbolMetadata(symbol=symbol)

    def enrich_yfinance(self, symbols: list[str], *, max_symbols: int = 25) -> int:
        self.enriched = bool(symbols and max_symbols)
        return len(symbols[:max_symbols])


class WatchlistProvider:
    def __init__(self) -> None:
        self.frames = _frames()
        self.frames["TEST"] = _watchlist_bars()

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


def test_broad_watchlist_ranks_without_rectangle_dependency() -> None:
    result = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )
    frame = watchlist_frame(result.candidates)

    assert result.total_symbols == 1
    assert result.candidates[0].source == "Broad"
    assert result.candidates[0].final_score > 0
    assert result.candidates[0].readiness_score > 0
    assert result.candidates[0].readiness_label in {
        "Ready Now",
        "Ready Watch",
        "Base Building",
        "Extended Risk",
        "Avoid",
    }
    assert "momentum_score" in frame.columns
    assert "readiness_label" in frame.columns
    assert "breakout_setup_score" in frame.columns
    assert "distance_to_trigger_pct" in frame.columns


def test_broad_watchlist_can_blend_rectangle_context(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    rectangle_provider = StaticProvider(_frames())
    watchlist_provider = WatchlistProvider()
    scan_result = ScannerEngine(rectangle_provider).scan_symbols(["TEST"], period="2y")
    SQLiteScanRepository(database).save_scan_run(scan_result)

    result = build_broad_watchlist(
        ["TEST"],
        watchlist_provider,
        repository=SQLiteScanRepository(database),
        period="2y",
        metadata_store=StaticMetadata(),
    )

    assert result.candidates[0].rectangle_score > 0
    assert result.candidates[0].source == "Broad + Rectangle"


def test_broad_watchlist_surfaces_actionable_setup_state() -> None:
    result = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=StaticMetadata(),
    )
    candidate = result.candidates[0]

    assert candidate.setup_state in {
        "Breakout",
        "Near Breakout",
        "Trending",
        "Base Building",
        "Extended",
        "No Clean Setup",
    }
    assert 0 <= candidate.breakout_setup_score <= 1
    assert 0 <= candidate.risk_score <= 1
    assert candidate.trigger_level > 0


def test_watchlist_failure_cache_round_trips_by_period(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_failures.csv"

    _write_failure_cache("2y", {"DEAD": "No price data"}, path=path)
    _write_failure_cache("1y", {"OTHER": "Short history"}, path=path)

    assert _read_failure_cache("2y", path=path) == {"DEAD": "No price data"}
    assert _read_failure_cache("1y", path=path) == {"OTHER": "Short history"}


def test_broad_watchlist_enriches_top_missing_metadata() -> None:
    result = build_broad_watchlist(
        ["TEST"],
        WatchlistProvider(),
        period="2y",
        metadata_store=EnrichingMetadata(),
    )

    assert result.candidates[0].name == "TEST Enriched"
    assert result.candidates[0].sector == "Industrials"
    assert result.candidates[0].industry == "Engineering"


def _watchlist_bars(rows: int = 260) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series([50 + index_num * 0.30 for index_num in range(rows)], index=index)
    volume = pd.Series([1_000_000 + index_num * 500 for index_num in range(rows)], index=index)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": volume,
        },
        index=index,
    )
