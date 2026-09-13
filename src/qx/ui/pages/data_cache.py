from pathlib import Path
from typing import Any

import pandas as pd

from qx.automation.morning import log_file_status, overnight_log_path
from qx.data.cache_status import (
    assess_cache_health,
    cache_operational_actions,
    list_bar_cache,
    summarize_bar_cache,
    universe_cache_coverage,
)
from qx.data.universe import UNIVERSE_OPTIONS, UniverseLoader
from qx.storage.pipeline import SQLitePipelineRepository
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.formatting import display_frame
from qx.ui.status import friendly_iso_time, render_cache_readiness_panel


SCAN_HISTORY_DB = "data/scanner_history.db"


def render_data_cache_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    period = streamlit.sidebar.selectbox("Cache period", ["2y", "3y", "5y"], index=0)
    universe_name = streamlit.sidebar.selectbox("Coverage universe", list(UNIVERSE_OPTIONS.keys()), index=4)

    summary = summarize_bar_cache()
    universe_symbols = UniverseLoader().load(UNIVERSE_OPTIONS[universe_name])
    coverage = universe_cache_coverage(universe_symbols, period=period)
    health = assess_cache_health(universe_symbols, period=period)
    overnight_log = log_file_status(overnight_log_path())
    latest_pipeline = _latest_pipeline_run()

    streamlit.subheader("Cache Readiness")
    render_cache_readiness_panel(streamlit, health=health, overnight_log=overnight_log)
    _render_pipeline_snapshot(streamlit, latest_pipeline)

    streamlit.subheader("Recommended Actions")
    render_bullet_list(streamlit, cache_action_items(health=health, coverage=coverage, latest_pipeline=latest_pipeline))

    metric_columns = streamlit.columns(4)
    metric_columns[0].metric("Files", summary.total_files)
    metric_columns[1].metric("Symbols", summary.total_symbols)
    metric_columns[2].metric("Size MB", summary.total_size_mb)
    metric_columns[3].metric("Periods", ", ".join(summary.periods.keys()) or "none")

    streamlit.subheader("Universe Coverage")
    streamlit.progress(coverage.coverage)
    streamlit.caption(
        f"{coverage.cached} of {coverage.total} symbols cached for {period}. "
        f"Missing: {coverage.missing}."
    )

    if coverage.missing:
        with streamlit.expander("Missing symbols"):
            streamlit.write(", ".join(coverage.missing_symbols[:300]))

    streamlit.subheader("Overnight Preload Commands")
    streamlit.code(
        ".\\.venv\\Scripts\\python.exe -m qx.interfaces.cli refresh-metadata",
        language="powershell",
    )
    streamlit.code(
        f".\\.venv\\Scripts\\python.exe -m qx.interfaces.cli warm-cache --universe {UNIVERSE_OPTIONS[universe_name]} --period {period} --refresh",
        language="powershell",
    )
    streamlit.code(
        ".\\scripts\\run_overnight_workflow.ps1",
        language="powershell",
    )

    streamlit.subheader("Recent Cache Files")
    rows = [
        {
            "symbol": item.symbol,
            "period": item.period,
            "rows": item.rows,
            "size_kb": round(item.size_bytes / 1000, 1),
            "modified_at": item.modified_at,
        }
        for item in list_bar_cache()
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        streamlit.info("No cached bar files found yet.")
    else:
        streamlit.dataframe(
            display_frame(frame.sort_values("modified_at", ascending=False), max_rows=100),
            width="stretch",
            hide_index=True,
        )


def _latest_pipeline_run() -> Any | None:
    runs = SQLitePipelineRepository(Path(SCAN_HISTORY_DB)).list_runs(limit=1)
    return runs[0] if runs else None


def _render_pipeline_snapshot(streamlit: Any, latest_pipeline: Any | None) -> None:
    streamlit.subheader("Latest Prep Pipeline")
    if latest_pipeline is None:
        streamlit.info("No saved prep pipeline run yet. Run Pipeline Control before relying on fast morning snapshots.")
        return
    cols = streamlit.columns(5)
    cols[0].metric("Run", latest_pipeline.id)
    cols[1].metric("Updated", friendly_iso_time(latest_pipeline.created_at))
    cols[2].metric("Universe", latest_pipeline.universe)
    cols[3].metric("Candidates", latest_pipeline.candidates)
    cols[4].metric("Issues", latest_pipeline.cache_failures + latest_pipeline.scan_failures)


def cache_action_items(*, health: Any, coverage: Any, latest_pipeline: Any | None) -> list[str]:
    actions = cache_operational_actions(health=health, coverage=coverage)

    if latest_pipeline is None:
        actions.append("Run the full prep pipeline once so Command Center can open from a saved morning snapshot.")
    else:
        issue_count = int(latest_pipeline.cache_failures) + int(latest_pipeline.scan_failures)
        if latest_pipeline.auth_warning:
            actions.append("Review Schwab auth before the next prep run; the latest pipeline had an auth warning.")
        if issue_count:
            actions.append(f"Review latest pipeline data issues: {issue_count} cache/scan failures were recorded.")
        if not issue_count and not latest_pipeline.auth_warning:
            actions.append("Latest prep pipeline is clean enough for operational use.")

    return actions

run_standalone_page(
    "Data Cache",
    "Review local market data coverage before running large scans.",
    render_data_cache_page,
)
