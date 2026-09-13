from pathlib import Path

import pandas as pd

from qx.models.market import BarDataRequest
from qx.models.scan import ScanRunResult
from qx.patterns.rectangle import analyze_rectangle
from qx.reports.daily_workflow import build_daily_workflow_report
from qx.storage.sqlite import SQLiteScanRepository
from tests.unit.test_rectangle import _clean_rectangle_bars


class StaticProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


def test_daily_workflow_combines_regime_sectors_and_watchlist(tmp_path: Path) -> None:
    repository = SQLiteScanRepository(tmp_path / "qx.db")
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    repository.save_scan_run(ScanRunResult(candidates=[candidate], total_symbols=1, passed_symbols=0))

    report = build_daily_workflow_report(
        provider=StaticProvider(_frames()),
        repository=repository,
        min_rank_score=0.0,
    )

    assert report.regime.label == "Risk On"
    assert report.sector_rotation.rows
    assert report.morning_report.top_candidates[0].symbol == "TEST"
    assert report.action_plan


def _frames() -> dict[str, pd.DataFrame]:
    symbols = [
        "SPY",
        "QQQ",
        "IWM",
        "XLC",
        "XLY",
        "XLP",
        "XLE",
        "XLF",
        "XLV",
        "XLI",
        "XLK",
        "XLB",
        "XLRE",
        "XLU",
    ]
    return {
        symbol: _bars(100.0, 0.35 if symbol in {"QQQ", "XLK"} else 0.20)
        for symbol in symbols
    }


def _bars(start: float, step: float, rows: int = 260) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series([start + index_num * step for index_num in range(rows)], index=index)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=index,
    )
