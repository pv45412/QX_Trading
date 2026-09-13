from pathlib import Path
from collections.abc import Sequence
from typing import Any

import pandas as pd

from qx.storage.pipeline import SQLitePipelineRepository, StoredPipelineRun
from qx.storage.workflow import SQLiteWorkflowRepository
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_workflow_history_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    limit = streamlit.sidebar.slider("Workflow runs", 5, 100, 25, 5)
    repository = SQLiteWorkflowRepository(SCAN_HISTORY_DB)
    runs = repository.list_runs(limit=int(limit))
    pipeline_runs = SQLitePipelineRepository(SCAN_HISTORY_DB).list_runs(limit=int(limit))

    streamlit.subheader("Workflow History")
    streamlit.caption("Compare saved daily workflow snapshots: regime, sectors, and watchlist changes.")
    if pipeline_runs:
        streamlit.subheader("Pipeline Runs")
        streamlit.dataframe(display_frame(_pipeline_frame(pipeline_runs)), width="stretch", hide_index=True)
        with streamlit.expander("Latest pipeline payload"):
            streamlit.json(pipeline_runs[0].payload)
    else:
        streamlit.info("No pipeline runs saved yet. Use Pipeline Control or overnight-workflow first.")

    if not runs:
        streamlit.info("No workflow runs saved yet. Use Daily Workflow, Pipeline Control, or overnight-workflow first.")
        return

    streamlit.subheader("Workflow Runs")
    frame = pd.DataFrame(
        [
            {
                "id": run.id,
                "created_at": run.created_at,
                "regime": run.regime_label,
                "risk": run.risk_level,
                "top_sectors": run.top_sectors,
                "top_symbols": run.top_symbols,
            }
            for run in runs
        ]
    )
    streamlit.dataframe(display_frame(frame), width="stretch", hide_index=True)

    comparison = repository.compare_latest()
    streamlit.subheader("Latest Change")
    if comparison.current is None:
        streamlit.info("No workflow comparison available.")
        return
    if comparison.previous is None:
        streamlit.info("Only one workflow run exists so far.")
        return

    cols = streamlit.columns(4)
    cols[0].metric("Regime Changed", "Yes" if comparison.regime_changed else "No")
    cols[1].metric("Risk Changed", "Yes" if comparison.risk_changed else "No")
    cols[2].metric("New Symbols", len(comparison.new_symbols))
    cols[3].metric("Removed Symbols", len(comparison.removed_symbols))

    change_rows = [
        {"type": "new_symbol", "value": symbol} for symbol in comparison.new_symbols
    ] + [
        {"type": "removed_symbol", "value": symbol} for symbol in comparison.removed_symbols
    ] + [
        {"type": "new_top_sector", "value": sector} for sector in comparison.new_top_sectors
    ] + [
        {"type": "removed_top_sector", "value": sector} for sector in comparison.removed_top_sectors
    ]
    if change_rows:
        streamlit.dataframe(display_frame(pd.DataFrame(change_rows)), width="stretch", hide_index=True)
    else:
        streamlit.success("No material workflow changes between the latest two runs.")

    latest_payload = comparison.current.payload
    with streamlit.expander("Latest action plan", expanded=True):
        for item in latest_payload.get("action_plan", []):
            streamlit.write(f"- {item}")


def _pipeline_frame(runs: Sequence[StoredPipelineRun]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": run.id,
                "created_at": run.created_at,
                "universe": run.universe,
                "period": run.period,
                "profile": run.profile,
                "data_source": run.data_source,
                "scan_run_id": run.scan_run_id,
                "workflow_run_id": run.workflow_run_id,
                "cached": run.cached_symbols,
                "cache_failures": run.cache_failures,
                "scanned": run.scanned_symbols,
                "candidates": run.candidates,
                "scan_failures": run.scan_failures,
                "regime": run.regime_label,
                "risk": run.risk_level,
                "auth_warning": run.auth_warning,
            }
            for run in runs
        ]
    )


run_standalone_page(
    "Workflow History",
    "Compare saved daily workflow snapshots over time.",
    render_workflow_history_page,
)
