from pathlib import Path

import pandas as pd
import pytest

from qx.data.metadata import SymbolMetadataStore
from qx.models.market import BarDataRequest
from qx.processing import overnight_workflow
from qx.brokers.schwab.auth import SchwabTokenManager
from qx.config.settings import Settings
from tests.unit.test_rectangle import _clean_rectangle_bars


class StaticProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


def test_overnight_workflow_refreshes_scans_and_saves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(overnight_workflow, "_symbols_for_scan", lambda universe: ["TEST"])
    monkeypatch.setattr(
        overnight_workflow,
        "_symbols_for_refresh",
        lambda universe: ["TEST", "SPY", "QQQ", "IWM", "ES=F", "XLK"],
    )
    monkeypatch.setattr(
        SymbolMetadataStore,
        "refresh_sp500",
        lambda self: 0,
    )

    result = overnight_workflow.run_overnight_workflow(
        provider=StaticProvider(_frames()),
        database=tmp_path / "qx.db",
    )

    assert result.cache_refresh.refreshed_symbols == 6
    assert result.scan_run_id == 1
    assert result.workflow_run_id == 1
    assert result.workflow_report.action_plan


def test_overnight_workflow_reports_schwab_auth_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(overnight_workflow, "_symbols_for_scan", lambda universe: ["TEST"])
    monkeypatch.setattr(
        overnight_workflow,
        "_symbols_for_refresh",
        lambda universe: ["TEST", "SPY", "QQQ", "IWM", "ES=F", "XLK"],
    )
    monkeypatch.setattr(
        SymbolMetadataStore,
        "refresh_sp500",
        lambda self: 0,
    )

    result = overnight_workflow.run_overnight_workflow(
        provider=StaticProvider(_frames()),
        database=tmp_path / "qx.db",
        token_manager=SchwabTokenManager(
            Settings(
                schwab_client_id="client",
                schwab_client_secret="secret",
                schwab_token_path=tmp_path / "missing.json",
            )
        ),
    )

    assert result.auth_warning


def _frames() -> dict[str, pd.DataFrame]:
    frames = {
        "TEST": _clean_rectangle_bars(),
        "SPY": _bars(100.0, 0.25),
        "QQQ": _bars(100.0, 0.40),
        "IWM": _bars(100.0, 0.20),
        "ES=F": _bars(5000.0, 8.0),
    }
    for symbol in ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLK", "XLB", "XLRE", "XLU"]:
        frames[symbol] = _bars(100.0, 0.15)
    return frames


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
