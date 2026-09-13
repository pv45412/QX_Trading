from pathlib import Path

import pytest

from qx.core.engine import ScannerEngine
from qx.options.ideas import OptionIdea
from qx.options.quality import FundamentalSnapshot
from qx.reports import command_center
from qx.reports.command_center import build_command_center, command_center_summary_frame, sector_focus_items
from qx.options.ideas import generate_option_ideas
from qx.storage.options import SQLiteOptionIdeaRepository
from qx.storage.sqlite import SQLiteScanRepository
from tests.unit.test_overnight_workflow import StaticProvider, _frames


class StaticFundamentalProvider:
    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        return FundamentalSnapshot(
            market_cap=75_000_000_000,
            eps_growth=0.18,
            revenue_growth=0.12,
            roe=0.25,
            debt_to_equity=0.35,
            profit_margin=0.20,
            free_cash_flow_positive=True,
        )


def test_command_center_builds_actionable_summary(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    provider = StaticProvider(_frames())
    scan_result = ScannerEngine(provider).scan_symbols(["TEST"], period="2y")
    scan_repository = SQLiteScanRepository(database)
    scan_repository.save_scan_run(scan_result)
    option_repository = SQLiteOptionIdeaRepository(database)
    option_repository.save_ideas(generate_option_ideas(scan_result.candidates))

    center = build_command_center(
        provider=provider,
        repository=scan_repository,
        period="2y",
        limit=5,
        watchlist_symbols=["SPY"],
        option_repository=option_repository,
    )
    frame = command_center_summary_frame(center)

    assert center.priorities
    assert center.action_plan
    assert center.spx.trend_bias
    assert center.watchlist
    assert center.saved_option_ideas
    assert center.saved_option_ideas[0].latest_underlying_price is not None
    assert center.saved_option_ideas[0].latest_return_pct is not None
    assert center.sector_focus
    assert not frame.empty
    assert any("ready" in str(detail).lower() for detail in frame["detail"])


def test_command_center_passes_fundamentals_to_directional_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "qx.db"
    provider = StaticProvider(_frames())
    scan_result = ScannerEngine(provider).scan_symbols(["TEST"], period="2y")
    scan_repository = SQLiteScanRepository(database)
    scan_repository.save_scan_run(scan_result)
    captured_market_cap = 0.0

    def fake_generate_directional_option_ideas(candidates, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_market_cap
        fundamentals = kwargs["fundamental_provider"].get_fundamentals("AAPL")
        captured_market_cap = fundamentals.market_cap or 0.0
        return [
            OptionIdea(
                symbol="AAPL",
                direction="Bullish",
                bucket="LEAPS",
                strategy="Long call",
                action="Watch",
                score=0.70,
                idea_score=0.70,
                contract_score=0.0,
                liquidity_score=0.80,
                setup_quality="Watch",
                liquidity_note="Liquid underlying",
                volatility_note="Normal",
                risk_note="Defined risk",
                rationale="Regression test",
                market_cap=captured_market_cap,
                quality_missing="",
            )
        ]

    monkeypatch.setattr(
        command_center,
        "generate_directional_option_ideas",
        fake_generate_directional_option_ideas,
    )

    center = build_command_center(
        provider=provider,
        repository=scan_repository,
        period="2y",
        limit=5,
        watchlist_symbols=["TEST"],
        fundamental_provider=StaticFundamentalProvider(),
    )

    assert center.directional_option_ideas
    assert center.directional_option_ideas[0].market_cap == 75_000_000_000
    assert captured_market_cap == 75_000_000_000
    assert center.directional_option_ideas[0].quality_missing != "real fundamentals unavailable"


def test_command_center_sector_focus_has_operational_lenses(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    provider = StaticProvider(_frames())
    scan_result = ScannerEngine(provider).scan_symbols(["TEST"], period="2y")
    scan_repository = SQLiteScanRepository(database)
    scan_repository.save_scan_run(scan_result)

    center = build_command_center(
        provider=provider,
        repository=scan_repository,
        period="2y",
        limit=5,
        watchlist_symbols=["SPY"],
    )
    focus = sector_focus_items(center.workflow.sector_rotation)

    assert {row["lens"] for row in focus} >= {"Leadership", "Crowding Risk", "Weak / Avoid"}
    assert all(row["symbols"] for row in focus)
    assert all(row["read"] for row in focus)
