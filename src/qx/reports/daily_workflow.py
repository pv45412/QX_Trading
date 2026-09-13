from dataclasses import dataclass

from qx.data.providers import MarketDataProvider
from qx.market.regime import MarketRegimeResult, analyze_market_regime
from qx.market.sector_rotation import SectorRotationResult, analyze_sector_rotation
from qx.reports.morning import MorningReport, build_morning_report
from qx.storage.sqlite import SQLiteScanRepository


@dataclass(frozen=True)
class DailyWorkflowReport:
    regime: MarketRegimeResult
    sector_rotation: SectorRotationResult
    morning_report: MorningReport
    action_plan: list[str]


def build_daily_workflow_report(
    *,
    provider: MarketDataProvider,
    repository: SQLiteScanRepository,
    period: str = "2y",
    min_rank_score: float = 0.55,
    limit: int = 25,
) -> DailyWorkflowReport:
    regime = analyze_market_regime(provider, period=period)
    sector_rotation = analyze_sector_rotation(provider, period=period)
    morning_report = build_morning_report(
        repository,
        min_rank_score=min_rank_score,
        limit=limit,
    )
    action_plan = _build_action_plan(regime, sector_rotation, morning_report)
    return DailyWorkflowReport(
        regime=regime,
        sector_rotation=sector_rotation,
        morning_report=morning_report,
        action_plan=action_plan,
    )


def _build_action_plan(
    regime: MarketRegimeResult,
    sector_rotation: SectorRotationResult,
    morning_report: MorningReport,
) -> list[str]:
    plan: list[str] = []
    leader_text = ", ".join(row.sector for row in sector_rotation.leaders) or "No sector leaders"

    if regime.label == "Risk On":
        plan.append("Use the scanner aggressively, but only for clean bases near resistance.")
        plan.append(f"Prioritize candidates inside leading sectors: {leader_text}.")
    elif regime.label == "Constructive":
        plan.append("Trade selectively and require strong pattern quality before taking alerts.")
        plan.append(f"Favor relative strength from these sectors: {leader_text}.")
    elif regime.label == "Choppy":
        plan.append("Reduce position size and wait for confirmed breakouts instead of early entries.")
        plan.append("Give failed breakouts extra weight because broad market follow-through is mixed.")
    else:
        plan.append("Treat new long ideas as watchlist only until the broad market improves.")
        plan.append("Focus on risk control, cash levels, and avoiding weak-sector breakouts.")

    if morning_report.near_breakout_candidates:
        symbols = ", ".join(candidate.symbol for candidate in morning_report.near_breakout_candidates[:5])
        plan.append(f"Set alerts for near-breakout names: {symbols}.")
    if morning_report.extended_leaders:
        symbols = ", ".join(candidate.symbol for candidate in morning_report.extended_leaders[:5])
        plan.append(f"Do not chase extended leaders without a new base: {symbols}.")
    if not morning_report.top_candidates:
        plan.append("Run a fresh nightly scan before making a watchlist decision.")

    return plan
