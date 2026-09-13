from pathlib import Path

import pandas as pd

from qx.models.market import BarDataRequest
from qx.models.scan import ScanRunResult
from qx.patterns.rectangle import analyze_rectangle
from qx.reports.daily_workflow import build_daily_workflow_report
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.workflow import SQLiteWorkflowRepository
from tests.unit.test_rectangle import _clean_rectangle_bars


class StaticProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


def test_workflow_repository_saves_and_compares_runs(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    scan_repository = SQLiteScanRepository(database)
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    scan_repository.save_scan_run(ScanRunResult(candidates=[candidate], total_symbols=1, passed_symbols=1))
    workflow_repository = SQLiteWorkflowRepository(database)

    first = build_daily_workflow_report(provider=StaticProvider(_frames(qqq_step=0.40)), repository=scan_repository)
    second = build_daily_workflow_report(provider=StaticProvider(_frames(qqq_step=-0.10)), repository=scan_repository)

    workflow_repository.save(first)
    workflow_repository.save(second)
    comparison = workflow_repository.compare_latest()

    assert comparison.current is not None
    assert comparison.previous is not None
    assert comparison.regime_changed
    assert comparison.current.top_symbols == "TEST"


def _frames(qqq_step: float) -> dict[str, pd.DataFrame]:
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
        symbol: _bars(100.0, qqq_step if symbol == "QQQ" else 0.20)
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
