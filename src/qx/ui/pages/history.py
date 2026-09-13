from pathlib import Path
from typing import Any

import pandas as pd

from qx.storage.sqlite import SQLiteScanRepository
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_history_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    repository = SQLiteScanRepository(SCAN_HISTORY_DB)
    runs = repository.list_scan_runs(limit=25)

    streamlit.subheader("Scan History")
    if not runs:
        streamlit.info("No saved scan runs yet. Run a scan first.")
        return

    streamlit.dataframe(
        display_frame(pd.DataFrame([run.__dict__ for run in runs])),
        width="stretch",
        hide_index=True,
    )

    streamlit.subheader("Latest Run Changes")
    changes = repository.compare_latest_runs()
    if not changes:
        streamlit.info("Need at least one saved run to show latest candidates.")
        return

    frame = pd.DataFrame([change.__dict__ for change in changes])
    if "score_change" in frame.columns:
        frame = frame.sort_values(["score_change", "current_score"], ascending=False, na_position="last")
    streamlit.dataframe(history_changes_frame(frame), width="stretch", hide_index=True)


def history_changes_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return display_frame(frame, columns=[
        "symbol", "current_score", "previous_score", "score_change",
        "current_quality", "previous_quality",
    ], max_rows=100)


run_standalone_page(
    "History",
    "Compare saved scan runs and see which symbols are improving.",
    render_history_page,
)
