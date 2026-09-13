import json
from pathlib import Path
from typing import Any

import pandas as pd

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.config.settings import get_settings
from qx.automation.morning import log_file_status, overnight_log_path
from qx.data.cache import CachedMarketDataProvider
from qx.data.cache_status import assess_cache_health
from qx.data.factory import (
    build_ema_timing_provider,
    build_fallback_market_data_provider,
    build_fundamental_provider,
    build_options_chain_provider,
)
from qx.data.universe import UNIVERSE_OPTIONS, UniverseLoader
from qx.market.sector_rotation import sector_rotation_frame
from qx.options.ideas import option_ideas_frame
from qx.processing.overnight_workflow import run_overnight_workflow
from qx.reports.command_center import build_command_center, command_center_summary_frame
from qx.storage.command_center import (
    CommandCenterSnapshotMetadata,
    SQLiteCommandCenterSnapshotRepository,
    StoredCommandCenterSnapshot,
    snapshot_freshness_label,
    snapshot_is_stale,
    command_center_payload,
)
from qx.reports.morning import morning_report_frame
from qx.storage.options import SQLiteOptionIdeaRepository, stored_option_ideas_frame
from qx.storage.pipeline import PipelineRunMetadata, SQLitePipelineRepository
from qx.storage.sqlite import SQLiteScanRepository
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.ai_evidence import render_ai_evidence_link
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, OPTION_CHAIN_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame, format_timestamp
from qx.ui.command_overview import render_command_overview
from qx.ui.metadata import displayed_candidate_metadata
from qx.ui.status import render_cache_readiness_panel
from qx.ui.today_state import render_today_identity, today_snapshots
from qx.ui.workspace_context import read_context, sync_context, workspace_url
from qx.watchlist.engine import watchlist_frame


SCAN_HISTORY_DB = Path("data/scanner_history.db")
SAVED_SCANNER_NAMES = "Saved scanner names"
COMMAND_WATCHLIST_COLUMNS = [
    "symbol",
    "name",
    "sector",
    "readiness_label",
    "setup_state",
    "readiness_score",
    "close",
    "trigger_level",
    "distance_to_trigger_pct",
    "breakout_setup_score",
    "momentum_score",
    "trend_score",
    "risk_score",
    "relative_volume_20d",
    "rectangle_status",
    "options_bias",
    "options_setup",
]


def render_command_center_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    context = read_context(getattr(streamlit, "query_params", {}))
    context_universe = next((name for name, code in UNIVERSE_OPTIONS.items() if code == context.get("universe")), "S&P 500")
    if context.get("universe") == "scanner_review":
        context_universe = SAVED_SCANNER_NAMES

    with streamlit.expander("Universe and data settings", expanded=False):
        command_cols = streamlit.columns([1.25, 0.8, 0.85, 0.9])
        watchlist_options = command_watchlist_options()
        watchlist_mode = command_cols[0].selectbox(
            "Watchlist Universe",
            watchlist_options,
            index=watchlist_options.index(context_universe),
            key="command_watchlist_universe",
        )
        period = command_cols[1].selectbox(
            "History",
            ["1y", "2y", "3y"],
            index=["1y", "2y", "3y"].index(context.get("period", "2y")) if context.get("period", "2y") in {"1y", "2y", "3y"} else 1,
            key="command_history",
        )
        data_source = command_cols[2].selectbox(
            "Market Data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
            key="command_data_source",
        )
        chain_source = command_cols[3].selectbox(
            "Options Data",
            OPTION_CHAIN_PROVIDER_OPTIONS,
            index=provider_index(OPTION_CHAIN_PROVIDER_OPTIONS),
            key="command_options_source",
        )
        with streamlit.expander("Ranking settings", expanded=False):
            setting_cols = streamlit.columns(2)
            min_rank_score = setting_cols[0].slider(
                "Minimum Rank",
                0.0,
                1.0,
                0.55,
                0.05,
                key="command_min_rank",
            )
            limit = setting_cols[1].slider(
                "Max Rows",
                5,
                100,
                25,
                5,
                key="command_max_rows",
            )

    snapshot_repository = SQLiteCommandCenterSnapshotRepository(SCAN_HISTORY_DB)
    selected_universe = "scanner_review" if watchlist_mode == SAVED_SCANNER_NAMES else UNIVERSE_OPTIONS[str(watchlist_mode)]
    if context.get("universe", selected_universe) != selected_universe or context.get("period", str(period)) != str(period):
        if "snapshot" in streamlit.query_params:
            del streamlit.query_params["snapshot"]
    sync_context(streamlit, universe=selected_universe, period=str(period))
    context = read_context(streamlit.query_params)
    try:
        matches = today_snapshots(snapshot_repository, context, data_source=str(data_source))
    except Exception:
        streamlit.error("The saved report could not be read. Review local data health before retrying.")
        return
    latest_snapshot = matches[0] if matches else None
    if latest_snapshot is not None:
        sync_context(streamlit, snapshot=str(latest_snapshot.id))
        render_today_identity(streamlit, latest_snapshot)
    if context.get("as_of"):
        streamlit.caption(f"Requested report cutoff: {context['as_of']} ET. This does not reconstruct market data for that date.")

    run_cols = streamlit.columns([1, 1, 3])
    refresh_clicked = run_cols[0].button("Refresh live", type="primary")
    run_cols[1].link_button("Preparation jobs", workspace_url("jobs", context, job_view="Pipeline"))
    _render_pipeline_status(run_cols[2])

    if not refresh_clicked:
        if latest_snapshot is None:
            streamlit.info("No saved report matches the selected universe, history, source, date, and snapshot. No refresh was started.")
            streamlit.link_button("Latest matching report", workspace_url("command_center", context, snapshot=""))
            return
        _render_snapshot(streamlit, latest_snapshot)
        render_ai_evidence_link(streamlit)
        streamlit.link_button("Report history", workspace_url("run_history", context, history_view="Snapshots"))
        return

    provider = CachedMarketDataProvider(build_fallback_market_data_provider(str(data_source)), refresh=True)
    try:
        chain_provider = build_options_chain_provider(str(chain_source))
    except Exception as exc:
        streamlit.warning(f"Option chain source unavailable: {exc}")
        chain_provider = None
    try:
        fundamental_provider = build_fundamental_provider(str(data_source))
    except Exception as exc:
        streamlit.warning(f"Fundamental source unavailable: {exc}")
        fundamental_provider = None
    try:
        timing_provider = build_ema_timing_provider(str(data_source))
    except Exception as exc:
        streamlit.warning(f"EMA timing source unavailable: {exc}")
        timing_provider = None

    repository = SQLiteScanRepository(SCAN_HISTORY_DB)
    watchlist_symbols = _watchlist_symbols_for_mode(str(watchlist_mode))

    with streamlit.spinner("Building morning command center..."):
        center = build_command_center(
            provider=provider,
            repository=repository,
            period=str(period),
            min_rank_score=float(min_rank_score),
            limit=int(limit),
            watchlist_symbols=watchlist_symbols,
            chain_provider=chain_provider,
            fundamental_provider=fundamental_provider,
            timing_provider=timing_provider,
            option_repository=SQLiteOptionIdeaRepository(SCAN_HISTORY_DB),
        )
    snapshot_id = snapshot_repository.save(
        center,
        CommandCenterSnapshotMetadata(
            source="live_refresh",
            period=str(period),
            data_source=str(data_source),
            universe=_snapshot_universe_label(str(watchlist_mode)),
        ),
    )
    streamlit.success(f"Saved live Command Center snapshot {snapshot_id}.")
    if "as_of" in streamlit.query_params:
        del streamlit.query_params["as_of"]
    sync_context(streamlit, snapshot=str(snapshot_id))

    render_command_overview(streamlit, command_center_payload(center, CommandCenterSnapshotMetadata(
        source="live_refresh", period=str(period), data_source=str(data_source),
        universe=_snapshot_universe_label(str(watchlist_mode)),
    )))


def _render_market_state(streamlit: Any, center: Any) -> None:
    streamlit.subheader("Today's Market State")
    cols = streamlit.columns(6)
    cols[0].metric("Regime", center.workflow.regime.label)
    cols[1].metric("Risk", center.workflow.regime.risk_level)
    cols[2].metric("SPX Bias", center.spx.trend_bias)
    cols[3].metric("Volatility", center.spx.volatility_context)
    cols[4].metric("SPY 20D", f"{center.workflow.regime.spy_return_20d:.1%}")
    cols[5].metric("ES Daily Move", f"{center.spx.es_overnight_move:.1%}" if center.spx.es_overnight_move is not None else "n/a")

    streamlit.dataframe(display_frame(command_center_summary_frame(center)), width="stretch", hide_index=True)

    streamlit.subheader("SPX / ES Action Plan")
    render_bullet_list(streamlit, center.spx.action_plan)
    with streamlit.expander("SPX Decision Levels"):
        render_bullet_list(streamlit, center.spx.decision_levels)


def _render_action_plan(streamlit: Any, center: Any) -> None:
    streamlit.subheader("Action Plan")
    priority_cols = streamlit.columns(2)
    with priority_cols[0]:
        streamlit.write("**Priorities**")
        render_bullet_list(streamlit, center.priorities)
    with priority_cols[1]:
        streamlit.write("**Operational Checklist**")
        render_bullet_list(streamlit, center.action_plan)


def _render_sector_leadership(streamlit: Any, center: Any) -> None:
    streamlit.subheader("Sector Leadership")
    _render_sector_focus(streamlit, center.sector_focus)
    sector_frame = sector_rotation_frame(center.workflow.sector_rotation)
    if sector_frame.empty:
        streamlit.info("No sector ETF data available.")
        return
    leaders = sector_frame.head(3)
    weak = sector_frame.tail(3).sort_values("leadership_score")
    cols = streamlit.columns(2)
    with cols[0]:
        streamlit.write("**Top sectors**")
        streamlit.dataframe(display_frame(leaders), width="stretch", hide_index=True)
    with cols[1]:
        streamlit.write("**Weakening sectors**")
        streamlit.dataframe(display_frame(weak), width="stretch", hide_index=True)
    with streamlit.expander("All sector rotation"):
        streamlit.dataframe(display_frame(sector_frame), width="stretch", hide_index=True)


def _render_top_watchlist(streamlit: Any, center: Any) -> None:
    streamlit.subheader("Top Broad Watchlist")
    watchlist = watchlist_frame(center.watchlist)
    _render_watchlist_metrics(streamlit, watchlist)
    streamlit.dataframe(
        _safe_display_frame(watchlist, columns=COMMAND_WATCHLIST_COLUMNS),
        width="stretch",
        hide_index=True,
    )

    with streamlit.expander("Rectangle Scanner Watchlist Context"):
        metadata_store, _ = displayed_candidate_metadata(
            center.workflow.morning_report.top_candidates,
            max_symbols=min(len(center.workflow.morning_report.top_candidates), 50),
        )
        streamlit.dataframe(
            display_frame(morning_report_frame(center.workflow.morning_report.top_candidates, metadata_store)),
            width="stretch",
            hide_index=True,
        )


def _render_options_desk(streamlit: Any, center: Any) -> None:
    streamlit.subheader("Options Desk")
    metrics = streamlit.columns(4)
    all_new_ideas = [*center.option_ideas, *center.directional_option_ideas]
    metrics[0].metric("New ideas", len(all_new_ideas))
    metrics[1].metric("Trade candidates", sum(idea.action == "Trade Candidate" for idea in all_new_ideas))
    metrics[2].metric("Saved watch", len(center.saved_option_ideas))
    movers = [idea for idea in center.saved_option_ideas if idea.latest_return_pct is not None and abs(idea.latest_return_pct) >= 0.05]
    metrics[3].metric("Saved movers", len(movers))

    tabs = streamlit.tabs(["New Directional Ideas", "Rectangle Ideas", "Saved Options", "Review Queue"])
    with tabs[0]:
        streamlit.dataframe(display_frame(option_ideas_frame(center.directional_option_ideas)), width="stretch", hide_index=True)
    with tabs[1]:
        streamlit.dataframe(display_frame(option_ideas_frame(center.option_ideas)), width="stretch", hide_index=True)
    with tabs[2]:
        streamlit.dataframe(
            display_frame(stored_option_ideas_frame(center.saved_option_ideas).drop(columns=["payload"], errors="ignore")),
            width="stretch",
            hide_index=True,
        )
    with tabs[3]:
        review_rows = _options_review_queue(center)
        if review_rows.empty:
            streamlit.success("No saved options ideas require immediate review.")
        else:
            streamlit.dataframe(display_frame(review_rows), width="stretch", hide_index=True)


def _options_review_queue(center: Any) -> pd.DataFrame:
    rows = []
    for idea in center.saved_option_ideas:
        reason = ""
        if idea.latest_return_pct is None:
            reason = "performance not refreshed"
        elif abs(idea.latest_return_pct) >= 0.05:
            reason = "material underlying move"
        if reason:
            rows.append(
                {
                    "symbol": idea.symbol,
                    "direction": idea.direction,
                    "strategy": idea.strategy,
                    "status": idea.status,
                    "latest_return_pct": idea.latest_return_pct,
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows)


def _render_snapshot_status(streamlit: Any, snapshot: StoredCommandCenterSnapshot | None) -> None:
    if snapshot is None:
        streamlit.warning("No morning snapshot saved yet. Command Center will need a live refresh.")
        return
    label = snapshot_freshness_label(snapshot)
    if snapshot_is_stale(snapshot):
        streamlit.warning(f"{label}. Snapshot may be stale; run prep pipeline or refresh live.")
    else:
        streamlit.caption(label)


def _render_cache_readiness(streamlit: Any, *, universe_label: str, period: str) -> None:
    try:
        universe_symbols = UniverseLoader().load(_universe_id_for_command_mode(universe_label))
        health = assess_cache_health(universe_symbols, period=period)
    except Exception as exc:
        streamlit.warning(f"Could not inspect local cache readiness: {exc}")
        return

    overnight_status = log_file_status(overnight_log_path())
    render_cache_readiness_panel(streamlit, health=health, overnight_log=overnight_status)


def _render_universe_context(
    streamlit: Any,
    *,
    selected_universe: str,
    snapshot: StoredCommandCenterSnapshot | None,
) -> None:
    if selected_universe == SAVED_SCANNER_NAMES:
        streamlit.caption(
            "Watchlist source: saved scanner names. Broad watchlist uses symbols from the latest stored scanner results."
        )
        return
    if snapshot is not None and not _same_command_universe(snapshot.universe, selected_universe):
        streamlit.info(
            f"Latest snapshot is for {snapshot.universe}. Use Refresh live or Run prep pipeline to build {selected_universe}."
        )


def _render_snapshot(streamlit: Any, snapshot: StoredCommandCenterSnapshot) -> None:
    render_command_overview(streamlit, snapshot.payload)


def _render_snapshot_legacy(streamlit: Any, snapshot: StoredCommandCenterSnapshot) -> None:
    payload = snapshot.payload
    summary = payload.get("summary", {})
    market_state = payload.get("market_state", {})
    spx = dict(market_state.get("spx") or {})
    regime = dict(market_state.get("regime") or {})

    streamlit.subheader("Today's Market State")
    cols = streamlit.columns(6)
    cols[0].metric("Regime", str(summary.get("regime_label", snapshot.regime_label)))
    cols[1].metric("Risk", str(summary.get("risk_level", snapshot.risk_level)))
    cols[2].metric("SPX Bias", str(summary.get("spx_bias", snapshot.spx_bias)))
    cols[3].metric("Volatility", str(summary.get("volatility_context", snapshot.volatility_context)))
    cols[4].metric("SPY 20D", _pct_text(regime.get("spy_return_20d")))
    cols[5].metric("ES Daily Move", _pct_text(spx.get("es_overnight_move")))
    streamlit.dataframe(display_frame(_snapshot_summary_frame(snapshot)), width="stretch", hide_index=True)

    streamlit.subheader("SPX / ES Action Plan")
    render_bullet_list(streamlit, [str(item) for item in spx.get("action_plan", [])])
    with streamlit.expander("SPX Decision Levels"):
        render_bullet_list(streamlit, [str(level) for level in spx.get("decision_levels", [])])

    streamlit.subheader("Action Plan")
    priority_cols = streamlit.columns(2)
    with priority_cols[0]:
        streamlit.write("**Priorities**")
        render_bullet_list(streamlit, [str(item) for item in payload.get("priorities", [])])
    with priority_cols[1]:
        streamlit.write("**Operational Checklist**")
        render_bullet_list(streamlit, [str(item) for item in payload.get("action_plan", [])])

    streamlit.subheader("Sector Leadership")
    _render_sector_focus(streamlit, payload.get("sector_focus", []))
    sector_frame = pd.DataFrame(payload.get("sectors", []))
    if sector_frame.empty:
        streamlit.info("No sector data in the saved snapshot.")
    else:
        cols = streamlit.columns(2)
        with cols[0]:
            streamlit.write("**Top sectors**")
            streamlit.dataframe(_safe_display_frame(sector_frame.head(3)), width="stretch", hide_index=True)
        with cols[1]:
            streamlit.write("**Weakening sectors**")
            streamlit.dataframe(
                _safe_display_frame(sector_frame.tail(3).sort_values("leadership_score")),
                width="stretch",
                hide_index=True,
            )
        with streamlit.expander("All sector rotation"):
            streamlit.dataframe(_safe_display_frame(sector_frame), width="stretch", hide_index=True)

    streamlit.subheader("Top Broad Watchlist")
    watchlist_frame_payload = pd.DataFrame(payload.get("watchlist", []))
    _render_watchlist_metrics(streamlit, watchlist_frame_payload)
    streamlit.dataframe(
        _safe_display_frame(watchlist_frame_payload, columns=COMMAND_WATCHLIST_COLUMNS),
        width="stretch",
        hide_index=True,
    )
    with streamlit.expander("Rectangle Scanner Watchlist Context"):
        streamlit.dataframe(
            _safe_display_frame(pd.DataFrame(payload.get("rectangle_watchlist", []))),
            width="stretch",
            hide_index=True,
        )

    streamlit.subheader("Options Desk")
    options = dict(payload.get("options", {}))
    tabs = streamlit.tabs(["New Directional Ideas", "Rectangle Ideas", "Saved Options", "Review Queue"])
    with tabs[0]:
        streamlit.dataframe(_safe_display_frame(pd.DataFrame(options.get("directional_ideas", []))), width="stretch", hide_index=True)
    with tabs[1]:
        streamlit.dataframe(_safe_display_frame(pd.DataFrame(options.get("rectangle_ideas", []))), width="stretch", hide_index=True)
    with tabs[2]:
        streamlit.dataframe(
            _safe_display_frame(pd.DataFrame(options.get("saved_ideas", [])).drop(columns=["payload"], errors="ignore")),
            width="stretch",
            hide_index=True,
        )
    with tabs[3]:
        review_rows = _snapshot_options_review_queue(options.get("saved_ideas", []))
        if review_rows.empty:
            streamlit.success("No saved options ideas require immediate review.")
        else:
            streamlit.dataframe(display_frame(review_rows), width="stretch", hide_index=True)


def _render_snapshot_preview(streamlit: Any, snapshot: StoredCommandCenterSnapshot) -> None:
    streamlit.subheader("Latest Snapshot")
    streamlit.caption("Fast mode: summary only. Use Load snapshot details when you need the full tables.")
    cols = streamlit.columns(6)
    cols[0].metric("Snapshot", f"#{snapshot.id}")
    cols[1].metric("Universe", snapshot.universe)
    cols[2].metric("Regime", snapshot.regime_label)
    cols[3].metric("Risk", snapshot.risk_level)
    cols[4].metric("Watchlist", snapshot.watchlist_count)
    cols[5].metric("Options", snapshot.option_ideas_count)
    streamlit.dataframe(display_frame(_snapshot_summary_frame(snapshot)), width="stretch", hide_index=True)


def _render_sector_focus(streamlit: Any, sector_focus: object) -> None:
    focus_frame = pd.DataFrame(sector_focus if isinstance(sector_focus, list) else [])
    if focus_frame.empty:
        return
    streamlit.write("**Sector Focus Board**")
    streamlit.dataframe(display_frame(focus_frame), width="stretch", hide_index=True)


def _snapshot_summary_frame(snapshot: StoredCommandCenterSnapshot) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"area": "Market Regime", "signal": snapshot.regime_label, "detail": snapshot.risk_level},
            {"area": "SPX Bias", "signal": snapshot.spx_bias, "detail": snapshot.volatility_context},
            {
                "area": "Watchlist",
                "signal": str(snapshot.watchlist_count),
                "detail": "broad multi-signal candidates",
            },
            {
                "area": "Options",
                "signal": str(snapshot.option_ideas_count),
                "detail": f"{snapshot.saved_options_count} saved watch ideas",
            },
        ]
    )


def _safe_display_frame(frame: pd.DataFrame, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Make snapshot payload frames safe for Streamlit/PyArrow display."""
    if frame.empty:
        return frame
    display = frame.copy()
    for column in display.columns:
        if display[column].dtype == "object":
            display[column] = display[column].map(_safe_cell_value)
    selected = _existing_columns(display, columns) if columns else list(display.columns)
    return display_frame(display, columns=selected)


def _render_watchlist_metrics(streamlit: Any, frame: pd.DataFrame) -> None:
    if frame.empty or "readiness_label" not in frame.columns:
        return
    counts = frame["readiness_label"].value_counts().to_dict()
    cols = streamlit.columns(5)
    cols[0].metric("Ready Now", int(counts.get("Ready Now", 0)))
    cols[1].metric("Ready Watch", int(counts.get("Ready Watch", 0)))
    cols[2].metric("Base Building", int(counts.get("Base Building", 0)))
    cols[3].metric("Extended Risk", int(counts.get("Extended Risk", 0)))
    cols[4].metric("Avoid", int(counts.get("Avoid", 0)))


def _existing_columns(frame: pd.DataFrame, columns: list[str] | None) -> list[str]:
    return [column for column in columns or [] if column in frame.columns]


def _safe_cell_value(value: object) -> object:
    if isinstance(value, dict | list | tuple | set):
        return json.dumps(value, default=str)
    return value


def _snapshot_options_review_queue(saved_ideas: object) -> pd.DataFrame:
    rows = []
    iterable = saved_ideas if isinstance(saved_ideas, list) else []
    for raw_idea in iterable:
        idea = dict(raw_idea)
        latest_return = idea.get("latest_return_pct")
        reason = ""
        if latest_return is None:
            reason = "performance not refreshed"
        elif abs(float(latest_return)) >= 0.05:
            reason = "material underlying move"
        if reason:
            rows.append(
                {
                    "symbol": idea.get("symbol", ""),
                    "direction": idea.get("direction", ""),
                    "strategy": idea.get("strategy", ""),
                    "status": idea.get("status", ""),
                    "latest_return_pct": latest_return,
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows)


def _pct_text(value: object) -> str:
    if value is None:
        return "n/a"
    if not isinstance(value, int | float | str):
        return "n/a"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "n/a"


def _render_pipeline_status(container: Any) -> None:
    latest = SQLitePipelineRepository(SCAN_HISTORY_DB).list_runs(limit=1)
    if not latest:
        container.info("No prep pipeline run saved yet.")
        return
    run = latest[0]
    container.caption(
        f"Latest pipeline: {format_timestamp(run.created_at)} | {run.universe} | candidates {run.candidates} | risk {run.risk_level}"
    )


def _run_prep_pipeline(
    streamlit: Any,
    *,
    universe_label: str,
    period: str,
    data_source: str,
    profile: str,
    refresh: bool,
    min_rank_score: float,
    limit: int,
) -> StoredCommandCenterSnapshot | None:
    universe = _universe_id_for_command_mode(universe_label)
    metadata = PipelineRunMetadata(
        universe=universe,
        period=period,
        profile=profile,
        data_source=data_source,
        lookback=40,
        max_range_pct=0.25,
        refresh=refresh,
    )
    with streamlit.spinner("Running prep pipeline. This can take several minutes for a large universe..."):
        result = run_overnight_workflow(
            provider=build_fallback_market_data_provider(data_source),
            universe=metadata.universe,
            period=metadata.period,
            profile=metadata.profile,
            lookback=metadata.lookback,
            max_range_pct=metadata.max_range_pct,
            refresh=metadata.refresh,
            database=SCAN_HISTORY_DB,
            token_manager=SchwabTokenManager(get_settings()),
        )
    run_id = SQLitePipelineRepository(SCAN_HISTORY_DB).save(result, metadata)
    streamlit.success(f"Prep pipeline saved as run {run_id}. Scan run {result.scan_run_id}; workflow run {result.workflow_run_id}.")
    with streamlit.spinner("Saving local morning Command Center snapshot..."):
        try:
            fundamental_provider = build_fundamental_provider(data_source)
        except Exception as exc:
            streamlit.warning(f"Fundamental source unavailable: {exc}")
            fundamental_provider = None
        try:
            timing_provider = build_ema_timing_provider(data_source)
        except Exception as exc:
            streamlit.warning(f"EMA timing source unavailable: {exc}")
            timing_provider = None
        center = build_command_center(
            provider=CachedMarketDataProvider(build_fallback_market_data_provider(data_source)),
            repository=SQLiteScanRepository(SCAN_HISTORY_DB),
            period=period,
            min_rank_score=min_rank_score,
            limit=limit,
            watchlist_symbols=_watchlist_symbols_for_mode(universe_label),
            fundamental_provider=fundamental_provider,
            timing_provider=timing_provider,
            option_repository=SQLiteOptionIdeaRepository(SCAN_HISTORY_DB),
        )
        snapshot_repository = SQLiteCommandCenterSnapshotRepository(SCAN_HISTORY_DB)
        snapshot_id = snapshot_repository.save(
            center,
            CommandCenterSnapshotMetadata(
                source="prep_pipeline",
                period=period,
                data_source=data_source,
                universe=_snapshot_universe_label(universe_label),
            ),
        )
    streamlit.success(f"Saved local morning snapshot {snapshot_id}.")
    return snapshot_repository.latest()


def command_watchlist_options() -> list[str]:
    return [SAVED_SCANNER_NAMES, *UNIVERSE_OPTIONS.keys()]


def _watchlist_symbols_for_mode(universe_label: str) -> list[str] | None:
    if universe_label == SAVED_SCANNER_NAMES:
        return None
    if universe_label in UNIVERSE_OPTIONS:
        return UniverseLoader().load(UNIVERSE_OPTIONS[universe_label])
    raise ValueError(f"Unsupported Command Center watchlist universe: {universe_label}")


def _universe_id_for_command_mode(universe_label: str) -> str:
    if universe_label == SAVED_SCANNER_NAMES:
        return UNIVERSE_OPTIONS["S&P 500"]
    if universe_label in UNIVERSE_OPTIONS:
        return UNIVERSE_OPTIONS[universe_label]
    raise ValueError(f"Unsupported Command Center prep universe: {universe_label}")


def _snapshot_universe_label(universe_label: str) -> str:
    if universe_label == SAVED_SCANNER_NAMES:
        return "Saved scanner names"
    return universe_label


def _same_command_universe(snapshot_universe: str, selected_universe: str) -> bool:
    if snapshot_universe == selected_universe:
        return True
    try:
        return snapshot_universe == _universe_id_for_command_mode(selected_universe)
    except ValueError:
        return False


run_standalone_page(
    "Command Center",
    "Morning decision page for regime, SPX, sectors, watchlist, and options.",
    render_command_center_page,
)
