from dataclasses import dataclass
from collections.abc import Sequence

import pandas as pd

from qx.data.fundamentals import FundamentalProvider
from qx.data.providers import MarketDataProvider
from qx.market.spx_dashboard import SpxDashboard, build_spx_dashboard
from qx.options.chains import OptionsChainProvider
from qx.options.ideas import OptionIdea, generate_directional_option_ideas, generate_option_ideas
from qx.options.timing import EmaTimingProvider
from qx.reports.daily_workflow import DailyWorkflowReport, build_daily_workflow_report
from qx.storage.options import SQLiteOptionIdeaRepository, StoredOptionIdea
from qx.storage.sqlite import SQLiteScanRepository
from qx.market.sector_rotation import SectorRotationResult
from qx.watchlist.engine import WatchlistCandidate, build_broad_watchlist


@dataclass(frozen=True)
class CommandCenter:
    workflow: DailyWorkflowReport
    spx: SpxDashboard
    watchlist: list[WatchlistCandidate]
    option_ideas: list[OptionIdea]
    directional_option_ideas: list[OptionIdea]
    saved_option_ideas: list[StoredOptionIdea]
    priorities: list[str]
    action_plan: list[str]
    sector_focus: list[dict[str, str]]


def build_command_center(
    *,
    provider: MarketDataProvider,
    repository: SQLiteScanRepository,
    period: str = "2y",
    min_rank_score: float = 0.55,
    limit: int = 25,
    watchlist_symbols: list[str] | None = None,
    chain_provider: OptionsChainProvider | None = None,
    fundamental_provider: FundamentalProvider | None = None,
    timing_provider: EmaTimingProvider | None = None,
    option_repository: SQLiteOptionIdeaRepository | None = None,
) -> CommandCenter:
    workflow = build_daily_workflow_report(
        provider=provider,
        repository=repository,
        period=period,
        min_rank_score=min_rank_score,
        limit=limit,
    )
    spx = build_spx_dashboard(provider, period=period)
    broad_watchlist = build_broad_watchlist(
        watchlist_symbols or [candidate.symbol for candidate in workflow.morning_report.top_candidates],
        provider,
        repository=repository,
        period=period,
        limit=limit,
    )
    option_ideas = generate_option_ideas(
        workflow.morning_report.top_candidates,
        limit=limit,
        chain_provider=chain_provider,
    )
    directional_option_ideas = generate_directional_option_ideas(
        broad_watchlist.candidates,
        limit=limit,
        min_directional_score=0.50,
        chain_provider=chain_provider,
        fundamental_provider=fundamental_provider,
        timing_provider=timing_provider,
    )
    if option_repository:
        option_repository.update_performance(provider, status="Watch", max_workers=8)
        saved_option_ideas = option_repository.list_ideas(status="Watch", limit=limit)
    else:
        saved_option_ideas = []
    priorities = _priorities(
        workflow,
        spx,
        broad_watchlist.candidates,
        option_ideas,
        directional_option_ideas,
        saved_option_ideas,
    )
    return CommandCenter(
        workflow=workflow,
        spx=spx,
        watchlist=broad_watchlist.candidates,
        option_ideas=option_ideas,
        directional_option_ideas=directional_option_ideas,
        saved_option_ideas=saved_option_ideas,
        priorities=priorities,
        action_plan=_command_action_plan(workflow, spx, broad_watchlist.candidates, saved_option_ideas),
        sector_focus=sector_focus_items(workflow.sector_rotation),
    )


def command_center_summary_frame(center: CommandCenter) -> pd.DataFrame:
    ready_now = _watchlist_count(center.watchlist, "Ready Now")
    ready_watch = _watchlist_count(center.watchlist, "Ready Watch")
    extended = _watchlist_count(center.watchlist, "Extended Risk")
    return pd.DataFrame(
        [
            {"area": "Market Regime", "signal": center.workflow.regime.label, "detail": center.workflow.regime.risk_level},
            {"area": "SPX Bias", "signal": center.spx.trend_bias, "detail": center.spx.volatility_context},
            {
                "area": "Watchlist",
                "signal": str(len(center.watchlist)),
                "detail": f"{ready_now} ready now, {ready_watch} ready watch, {extended} extended risk",
            },
            {
                "area": "Options",
                "signal": str(
                    sum(idea.action == "Trade Candidate" for idea in center.option_ideas)
                    + sum(idea.action == "Trade Candidate" for idea in center.directional_option_ideas)
                ),
                "detail": f"{len(center.saved_option_ideas)} saved watch ideas",
            },
        ]
    )


def sector_focus_items(sector_rotation: SectorRotationResult) -> list[dict[str, str]]:
    if not sector_rotation.rows:
        return []
    leaders = sector_rotation.rows[:3]
    improving = [row for row in sector_rotation.rows if row.rotation_status in {"Improving", "Early Turn"}][:3]
    crowded = sorted(sector_rotation.rows, key=lambda row: row.extension_risk_score, reverse=True)[:3]
    weak = sorted(sector_rotation.rows, key=lambda row: (row.leadership_score, row.relative_20d))[:3]
    rows = [
        {
            "lens": "Leadership",
            "symbols": _sector_symbols(leaders),
            "read": "Money is already concentrated here; prioritize clean pullbacks and confirmed breakouts.",
        },
        {
            "lens": "Improving",
            "symbols": _sector_symbols(improving),
            "read": "Rotation is starting to improve; look for early watchlist names before they become crowded.",
        },
        {
            "lens": "Crowding Risk",
            "symbols": _sector_symbols(crowded),
            "read": "Strong but extended; avoid chasing and prefer retests or lower-risk option structures.",
        },
        {
            "lens": "Weak / Avoid",
            "symbols": _sector_symbols(weak),
            "read": "Capital is lagging here; demand exceptional stock-specific strength before acting.",
        },
    ]
    return [row for row in rows if row["symbols"]]


def _priorities(
    workflow: DailyWorkflowReport,
    spx: SpxDashboard,
    watchlist: list[WatchlistCandidate],
    option_ideas: list[OptionIdea],
    directional_option_ideas: list[OptionIdea],
    saved_option_ideas: list[StoredOptionIdea],
) -> list[str]:
    priorities: list[str] = []
    if workflow.regime.risk_level == "Low":
        priorities.append("Market backdrop supports selective breakout trades.")
    elif workflow.regime.risk_level == "High":
        priorities.append("Defensive market backdrop: reduce size and demand confirmation.")
    else:
        priorities.append("Use normal risk with strict invalidation levels.")

    priorities.append(f"SPX bias: {spx.trend_bias}; key boundary is prior range.")
    top_sectors = ", ".join(row.sector for row in workflow.sector_rotation.leaders[:3])
    if top_sectors:
        priorities.append(f"Favor leading sectors: {top_sectors}.")

    ready_now = [candidate.symbol for candidate in watchlist if candidate.readiness_label == "Ready Now"]
    ready_watch = [candidate.symbol for candidate in watchlist if candidate.readiness_label == "Ready Watch"]
    extended = [candidate.symbol for candidate in watchlist if candidate.readiness_label == "Extended Risk"]
    if ready_now:
        priorities.append(f"Ready now broad watchlist: {', '.join(ready_now[:5])}.")
    elif ready_watch:
        priorities.append(f"Ready watch broad names: {', '.join(ready_watch[:5])}.")
    if extended:
        priorities.append(f"Avoid chasing extended risk names: {', '.join(extended[:5])}.")

    all_ideas = [*option_ideas, *directional_option_ideas]
    trade_ideas = [idea.symbol for idea in all_ideas if idea.action == "Trade Candidate"]
    if trade_ideas:
        priorities.append(f"Options candidates to inspect: {', '.join(trade_ideas[:5])}.")
    elif saved_option_ideas:
        symbols = ", ".join(idea.symbol for idea in saved_option_ideas[:5])
        priorities.append(f"Review saved options watchlist: {symbols}.")
    elif watchlist and not (ready_now or ready_watch):
        symbols = ", ".join(candidate.symbol for candidate in watchlist[:5])
        priorities.append(f"Top broad watchlist names need confirmation: {symbols}.")
    elif workflow.morning_report.near_breakout_candidates:
        symbols = ", ".join(candidate.symbol for candidate in workflow.morning_report.near_breakout_candidates[:5])
        priorities.append(f"Set breakout alerts first: {symbols}.")
    else:
        priorities.append("No clean trade candidates yet; keep scan results on watch.")

    return priorities


def _sector_symbols(rows: Sequence[object]) -> str:
    labels = []
    for row in rows:
        sector = getattr(row, "sector", "")
        etf = getattr(row, "etf", "")
        if sector and etf:
            labels.append(f"{sector} ({etf})")
    return ", ".join(labels)


def _command_action_plan(
    workflow: DailyWorkflowReport,
    spx: SpxDashboard,
    watchlist: list[WatchlistCandidate],
    saved_option_ideas: list[StoredOptionIdea],
) -> list[str]:
    plan = [*workflow.action_plan, *spx.action_plan]
    ready_symbols = [
        candidate.symbol
        for candidate in watchlist
        if candidate.readiness_label in {"Ready Now", "Ready Watch"}
    ]
    if ready_symbols:
        plan.append(f"Set trigger alerts for ready broad watchlist names: {', '.join(ready_symbols[:5])}.")
    elif watchlist:
        symbols = ", ".join(candidate.symbol for candidate in watchlist[:5])
        plan.append(f"Chart review only; no broad names are ready yet: {symbols}.")
    if saved_option_ideas:
        review = [
            idea.symbol
            for idea in saved_option_ideas
            if idea.latest_return_pct is None or abs(idea.latest_return_pct) >= 0.05
        ]
        if review:
            plan.append(f"Review saved options ideas with stale or material moves: {', '.join(review[:5])}.")
    if workflow.regime.risk_level == "High":
        plan.append("Avoid chasing extended breakouts; require confirmed follow-through and defined risk.")
    else:
        plan.append("Run cache/pipeline before the open if data is stale, then refresh Command Center.")
    return _dedupe(plan)


def _watchlist_count(watchlist: list[WatchlistCandidate], label: str) -> int:
    return sum(candidate.readiness_label == label for candidate in watchlist)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output
