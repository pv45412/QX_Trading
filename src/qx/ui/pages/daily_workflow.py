from pathlib import Path
from typing import Any

import pandas as pd

from qx.data.cache import CachedMarketDataProvider
from qx.data.factory import build_fallback_market_data_provider
from qx.market.regime import market_regime_frame
from qx.market.sector_rotation import sector_rotation_frame
from qx.reports.daily_workflow import DailyWorkflowReport, build_daily_workflow_report
from qx.reports.morning import morning_report_frame
from qx.storage.options import SQLiteOptionIdeaRepository, StoredOptionIdea, stored_option_ideas_frame
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.workflow import SQLiteWorkflowRepository
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.metadata import displayed_candidate_metadata


SCAN_HISTORY_DB = Path("data/scanner_history.db")
OPTIONS_WATCHLIST_COLUMNS = [
    "symbol",
    "status",
    "direction",
    "strategy",
    "action",
    "entry_underlying_price",
    "latest_underlying_price",
    "latest_return_pct",
    "idea_score",
    "created_at",
]


def render_daily_workflow_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    period = streamlit.sidebar.selectbox(
        "Workflow market history",
        ["1y", "2y", "5y"],
        index=1,
    )
    min_rank_score = streamlit.sidebar.slider("Workflow min rank", 0.0, 1.0, 0.55, 0.05)
    limit = streamlit.sidebar.slider("Workflow max rows", 5, 100, 25, 5)
    data_source = streamlit.sidebar.selectbox(
        "Workflow data source",
        MARKET_DATA_PROVIDER_OPTIONS,
        index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
    )

    streamlit.subheader("Daily Workflow")
    streamlit.caption(
        "Market regime -> sector leadership -> watchlist rank -> technical scanner action plan."
    )

    if streamlit.button("Build workflow"):
        with streamlit.spinner("Building daily workflow..."):
            report = build_daily_workflow_report(
                provider=CachedMarketDataProvider(build_fallback_market_data_provider(str(data_source))),
                repository=SQLiteScanRepository(SCAN_HISTORY_DB),
                period=str(period),
                min_rank_score=float(min_rank_score),
                limit=int(limit),
            )
            workflow_run_id = SQLiteWorkflowRepository(SCAN_HISTORY_DB).save(report)
        streamlit.session_state["today_workflow_result"] = (report, str(data_source), workflow_run_id)

    saved = streamlit.session_state.get("today_workflow_result")
    if saved is not None:
        report, saved_source, run_id = saved
        streamlit.caption(f"Displayed workflow run {run_id}. Requested source: {saved_source}.")
        _render_report(streamlit, report, data_source=saved_source)
    else:
        streamlit.info("Build a workflow to create and save a preparation plan. Saved run changes are available below.")

    comparison = SQLiteWorkflowRepository(SCAN_HISTORY_DB).compare_latest()
    if comparison.current is not None:
        with streamlit.expander("Latest workflow comparison"):
            streamlit.write(f"Current run: {comparison.current.id} at {comparison.current.created_at}")
            if comparison.previous is None:
                streamlit.info("No previous workflow run to compare yet.")
            else:
                streamlit.write(f"Previous run: {comparison.previous.id} at {comparison.previous.created_at}")
                streamlit.write(f"- Regime changed: {comparison.regime_changed}")
                streamlit.write(f"- Risk changed: {comparison.risk_changed}")
                streamlit.write(f"- New symbols: {', '.join(comparison.new_symbols) or 'None'}")
                streamlit.write(f"- Removed symbols: {', '.join(comparison.removed_symbols) or 'None'}")
                streamlit.write(f"- New top sectors: {', '.join(comparison.new_top_sectors) or 'None'}")


def _render_report(streamlit: Any, typed_report: DailyWorkflowReport, *, data_source: str) -> None:
    metric_cols = streamlit.columns(4)
    metric_cols[0].metric("Regime", typed_report.regime.label)
    metric_cols[1].metric("Risk", typed_report.regime.risk_level)
    metric_cols[2].metric("SPY 20D", f"{typed_report.regime.spy_return_20d:.1%}")
    metric_cols[3].metric("Realized Vol", f"{typed_report.regime.realized_vol_20d:.1%}")

    streamlit.subheader("Preparation plan")
    render_bullet_list(streamlit, typed_report.action_plan)
    with streamlit.expander("Market evidence"):
        regime_frame = market_regime_frame(typed_report.regime)
        streamlit.dataframe(display_frame(regime_frame, columns=list(regime_frame.columns)), width="stretch", hide_index=True)
        render_bullet_list(streamlit, typed_report.regime.notes)

    streamlit.subheader("Sector Leadership")
    sector_frame = sector_rotation_frame(typed_report.sector_rotation)
    if sector_frame.empty:
        streamlit.info("No sector ETF data available.")
    else:
        streamlit.dataframe(display_frame(sector_frame, columns=["etf", "sector", "relative_5d", "relative_20d", "rotation_status"]), width="stretch", hide_index=True)
    if typed_report.sector_rotation.failures:
        with streamlit.expander("Sector data failures"):
            streamlit.json(typed_report.sector_rotation.failures)

    streamlit.subheader("Scanner Watchlist")
    morning = typed_report.morning_report
    if morning.run is None:
        streamlit.info("No saved scan run found. Run Scanner or nightly-scan first.")
        return
    streamlit.caption(f"Using saved scan run {morning.run.id} from {morning.run.created_at}.")

    metadata_store, _ = displayed_candidate_metadata(
        morning.top_candidates,
        max_symbols=min(len(morning.top_candidates), 50),
    )

    top_frame = morning_report_frame(morning.top_candidates, metadata_store)
    streamlit.dataframe(display_frame(top_frame, columns=["symbol", "status", "rank_score", "distance_to_resistance", "relative_volume_20d", "weekly_status"]), width="stretch", hide_index=True)
    with streamlit.expander("Near Breakout"):
        streamlit.dataframe(
            display_frame(morning_report_frame(morning.near_breakout_candidates, metadata_store)),
            width="stretch",
            hide_index=True,
        )
    with streamlit.expander("Extended Leaders"):
        streamlit.dataframe(
            display_frame(morning_report_frame(morning.extended_leaders, metadata_store)),
            width="stretch",
            hide_index=True,
        )

    _render_options_watchlist(streamlit, data_source=data_source)


def _render_options_watchlist(streamlit: Any, *, data_source: str) -> None:
    streamlit.subheader("Options Watchlist")
    repository = SQLiteOptionIdeaRepository(SCAN_HISTORY_DB)
    saved_options = repository.list_ideas(status="Watch", limit=25)
    if not saved_options:
        streamlit.info("No saved options ideas yet. Build and save ideas from the Options Ideas page.")
    else:
        updated = 0
        if streamlit.button("Refresh saved option prices", key="workflow_refresh_options"):
            try:
                updated = repository.update_performance(
                    CachedMarketDataProvider(build_fallback_market_data_provider(data_source)),
                    status="Watch",
                    max_workers=8,
                )
            except Exception as exc:
                streamlit.warning(f"Could not refresh saved options performance from {data_source}: {exc}")
                updated = 0

        saved_options = repository.list_ideas(status="Watch", limit=25)
        if updated:
            streamlit.caption(f"Updated {updated} saved option performance snapshot(s).")
        missing_prices = sum(idea.latest_underlying_price is None for idea in saved_options)
        if missing_prices:
            streamlit.caption(f"{missing_prices} saved idea(s) still need price data from {data_source}.")
        streamlit.dataframe(_options_watchlist_display_frame(saved_options), width="stretch", hide_index=True)


def _options_watchlist_display_frame(saved_options: list[StoredOptionIdea]) -> pd.DataFrame:
    options_frame = stored_option_ideas_frame(saved_options).drop(columns=["payload"], errors="ignore")
    return display_frame(options_frame, columns=OPTIONS_WATCHLIST_COLUMNS)


run_standalone_page(
    "Daily Workflow",
    "Combine market regime, sector leadership, and saved scan results.",
    render_daily_workflow_page,
)
