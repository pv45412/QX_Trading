from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from qx.data.cache_status import summarize_bar_cache, universe_cache_coverage
from qx.data.universe import UNIVERSE_OPTIONS, UniverseLoader
from qx.storage.options import SQLiteOptionIdeaRepository, option_idea_performance_frame, stored_option_ideas_frame
from qx.storage.pipeline import SQLitePipelineRepository
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.workflow import SQLiteWorkflowRepository
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_performance_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    _render_options_performance(streamlit)


def render_system_readiness(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    period = streamlit.sidebar.selectbox("Readiness period", ["2y", "3y", "5y"], index=0)
    universe_name = streamlit.sidebar.selectbox("Readiness universe", list(UNIVERSE_OPTIONS.keys()), index=4)

    streamlit.subheader("Performance Readiness")
    streamlit.caption("Checks whether the app can run from local data instead of live downloads.")

    summary = summarize_bar_cache()
    symbols = UniverseLoader().load(UNIVERSE_OPTIONS[universe_name])
    coverage = universe_cache_coverage(symbols, period=str(period))
    scan_runs = SQLiteScanRepository(SCAN_HISTORY_DB).list_scan_runs(limit=1)
    workflow_runs = SQLiteWorkflowRepository(SCAN_HISTORY_DB).list_runs(limit=1)
    pipeline_runs = SQLitePipelineRepository(SCAN_HISTORY_DB).list_runs(limit=1)

    cols = streamlit.columns(6)
    cols[0].metric("Cache Files", summary.total_files)
    cols[1].metric("Cache MB", summary.total_size_mb)
    cols[2].metric("Coverage", f"{coverage.coverage:.0%}")
    cols[3].metric("Latest Scan", scan_runs[0].id if scan_runs else "none")
    cols[4].metric("Latest Workflow", workflow_runs[0].id if workflow_runs else "none")
    cols[5].metric("Latest Pipeline", pipeline_runs[0].id if pipeline_runs else "none")

    readiness = _readiness_score(
        coverage.coverage,
        bool(scan_runs),
        bool(workflow_runs),
        bool(pipeline_runs),
    )
    streamlit.progress(readiness)
    streamlit.caption(f"Readiness score: {readiness:.0%}")

    recommendations = _recommendations(
        coverage.coverage,
        bool(scan_runs),
        bool(workflow_runs),
        bool(pipeline_runs),
        period,
    )
    streamlit.subheader("Recommended Actions")
    for item in recommendations:
        streamlit.write(f"- {item}")

    streamlit.subheader("Fast Morning Commands")
    streamlit.code(
        f".\\.venv\\Scripts\\python.exe -m qx.interfaces.cli overnight-workflow --universe {UNIVERSE_OPTIONS[universe_name]} --period {period}",
        language="powershell",
    )
    streamlit.code(
        "powershell -ExecutionPolicy Bypass -File scripts\\schedule_overnight_workflow.ps1",
        language="powershell",
    )

    status_frame = pd.DataFrame(
        [
            {
                "check": "bar_cache_coverage",
                "status": "pass" if coverage.coverage >= 0.90 else "needs_work",
                "details": f"{coverage.cached}/{coverage.total} cached for {period}",
            },
            {
                "check": "latest_pipeline_run",
                "status": "pass" if pipeline_runs else "missing",
                "details": pipeline_runs[0].created_at if pipeline_runs else "No pipeline run saved.",
            },
            {
                "check": "latest_scan_run",
                "status": "pass" if scan_runs else "missing",
                "details": scan_runs[0].created_at if scan_runs else "No scan run saved.",
            },
            {
                "check": "latest_workflow_run",
                "status": "pass" if workflow_runs else "missing",
                "details": workflow_runs[0].created_at if workflow_runs else "No workflow run saved.",
            },
        ]
    )
    streamlit.dataframe(display_frame(status_frame), width="stretch", hide_index=True)


def _readiness_score(
    cache_coverage: float,
    has_scan: bool,
    has_workflow: bool,
    has_pipeline: bool,
) -> float:
    score = cache_coverage * 0.50
    score += 0.20 if has_scan else 0.0
    score += 0.20 if has_workflow else 0.0
    score += 0.10 if has_pipeline else 0.0
    return min(score, 1.0)


def _recommendations(
    cache_coverage: float,
    has_scan: bool,
    has_workflow: bool,
    has_pipeline: bool,
    period: object,
) -> list[str]:
    recommendations: list[str] = []
    if cache_coverage < 0.90:
        recommendations.append(f"Run overnight workflow or warm-cache to raise {period} local coverage.")
    if not has_scan:
        recommendations.append("Run a scan and save it so dashboards can read local results.")
    if not has_workflow:
        recommendations.append("Save a daily workflow run so history comparisons become available.")
    if not has_pipeline:
        recommendations.append("Run Pipeline Control once so operational run history is available.")
    if not recommendations:
        recommendations.append("Local data is ready for a fast morning review.")
    return recommendations


def _render_options_performance(streamlit: Any) -> None:
    repository = SQLiteOptionIdeaRepository(SCAN_HISTORY_DB)
    streamlit.subheader("Idea Tracking")
    streamlit.warning(
        "Research ideas only. Underlying-stock returns are not actual option P&L or trade returns. "
        "These snapshots contain no contract fills, option marks, position sizes, or trading fees."
    )
    streamlit.caption(
        "Underlying Return = latest saved underlying price / price when the idea was saved - 1. "
        "It is not adjusted for a bearish thesis. Snapshot time is recording time, not a verified "
        "market-bar timestamp; prices may be historical."
    )
    try:
        summary = repository.tracking_counts()
    except (sqlite3.Error, OSError):
        streamlit.error("Idea tracking could not be read. No price refresh was started.")
        return

    cols = streamlit.columns(3)
    cols[0].metric("Saved Ideas", summary["saved_ideas"])
    cols[1].metric("Underlying Snapshots", summary["performance_snapshots"])
    cols[2].metric("Tracked Ideas", summary["tracked_ideas"])
    streamlit.caption("Counts cover all saved records. Tracked Ideas counts distinct saved idea IDs.")
    if not summary["saved_ideas"]:
        streamlit.info("No saved research ideas. No trades are inferred from qx signals.")
        return

    page_size = 25
    page = int(streamlit.number_input(
        "Ideas page", min_value=1,
        max_value=max(1, (summary["saved_ideas"] + page_size - 1) // page_size),
        value=1, step=1, key="idea_tracking_page",
    ))
    try:
        saved = repository.list_ideas(limit=page_size, offset=(page - 1) * page_size)
        history = repository.list_performance(limit=100)
    except (sqlite3.Error, OSError):
        streamlit.error("Saved idea records could not be read.")
        return

    saved_frame = stored_option_ideas_frame(saved).drop(columns=["payload"], errors="ignore")
    streamlit.dataframe(_idea_tracking_frame(saved_frame), width="stretch", hide_index=True)
    if history:
        with streamlit.expander("Latest 100 underlying-price snapshots"):
            streamlit.dataframe(
                _idea_tracking_frame(option_idea_performance_frame(history)),
                width="stretch",
                hide_index=True,
            )


def _idea_tracking_frame(frame: pd.DataFrame) -> pd.DataFrame:
    # Explicit columns keep stable idea IDs visible, including repeated-symbol ideas.
    return display_frame(frame, columns=list(frame.columns)).rename(columns={
        "Id": "Record ID", "Option Idea Id": "Idea ID", "Created": "Recorded At",
        "Entry Price": "Underlying Price at Save", "Latest Price": "Latest Underlying Price",
        "Latest Return": "Underlying Return", "Return": "Underlying Return",
        "Underlying Price": "Snapshot Underlying Price",
    })


def _options_performance_summary(
    *, saved_count: int, history_count: int, tracked_count: int
) -> dict[str, int]:
    return {
        "saved_ideas": saved_count,
        "performance_snapshots": history_count,
        "tracked_ideas": tracked_count,
    }


run_standalone_page(
    "Idea Tracking",
    "Saved research ideas and underlying-stock returns, not actual option P&L.",
    render_performance_page,
)
