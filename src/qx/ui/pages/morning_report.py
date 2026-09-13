from pathlib import Path
from typing import Any

import pandas as pd

from qx.data.metadata import SymbolMetadataStore
from qx.models.scan import ScanCandidate
from qx.reports.morning import build_morning_report, morning_report_frame, sector_summary_frame
from qx.storage.sqlite import SQLiteScanRepository
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import format_timestamp
from qx.ui.metadata import displayed_candidate_metadata


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_morning_report_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    min_rank_score = streamlit.sidebar.slider("Report min rank", 0.0, 1.0, 0.55, 0.05)
    limit = streamlit.sidebar.slider("Report max rows", 5, 100, 25, 5)
    repository = SQLiteScanRepository(SCAN_HISTORY_DB)
    report = build_morning_report(repository, min_rank_score=min_rank_score, limit=limit)

    streamlit.subheader("Morning Report")
    if report.run is None:
        streamlit.info("No saved scan runs yet. Run a nightly scan or use the Scanner page.")
        return

    metadata_store, enriched_count = displayed_candidate_metadata(
        report.top_candidates,
        max_symbols=min(limit, 25),
    )

    previous = f" vs previous run {report.previous_run.id}" if report.previous_run else ""
    streamlit.caption(f"Latest run {report.run.id} created {_format_run_time(report.run.created_at)}{previous}.")
    streamlit.caption("Bar/session date and provider retrieval time are not recorded in this saved scan.")

    unknown_sector_count = _unknown_sector_count(report.top_candidates, metadata_store)
    metrics = streamlit.columns(6)
    metrics[0].metric("Review List", len(report.top_candidates))
    metrics[1].metric("New", len(report.new_candidates))
    metrics[2].metric("Improving", len(report.improving_candidates))
    metrics[3].metric("Near Trigger", len(report.near_breakout_candidates))
    metrics[4].metric("Extended", len(report.extended_leaders))
    metrics[5].metric("Data Gaps", unknown_sector_count)

    if enriched_count:
        streamlit.caption(f"Updated metadata for {enriched_count} displayed candidate(s).")
    _review_focus(streamlit, report, unknown_sector_count)
    buckets = {
        "Top Candidates": report.top_candidates,
        "New Candidates": report.new_candidates,
        "Improving Candidates": report.improving_candidates,
        "Near Breakout": report.near_breakout_candidates,
        "Extended Leaders": report.extended_leaders,
    }
    selected = streamlit.selectbox("Candidate group", list(buckets), key="morning_candidate_group")
    _section(streamlit, selected, buckets[selected], metadata_store)
    _diagnostics_section(streamlit, "Selected group diagnostics", buckets[selected], metadata_store)
    sector_frame = sector_summary_frame(report.top_candidates, metadata_store)
    if sector_frame.empty:
        streamlit.info("No sector data available.")
    else:
        if unknown_sector_count:
            streamlit.warning(
                f"{unknown_sector_count} top candidates are missing sector metadata. "
                "Refresh symbol metadata from the Data Cache page or the prep pipeline."
            )
        with streamlit.expander("Sector distribution"):
            streamlit.dataframe(_sector_display_frame(sector_frame), width="stretch", hide_index=True)


def _section(
    streamlit: Any,
    title: str,
    candidates: list[ScanCandidate],
    metadata_store: SymbolMetadataStore,
) -> None:
    frame = morning_report_frame(candidates, metadata_store)
    with streamlit.container():
        if frame.empty:
            streamlit.info("No symbols in this bucket.")
        else:
            streamlit.dataframe(_candidate_display_frame(frame), width="stretch", hide_index=True)
            streamlit.download_button(
                f"Download {title} CSV",
                frame.to_csv(index=False),
                file_name=f"{title.lower().replace(' ', '_')}.csv",
                mime="text/csv",
            )


def _review_focus(streamlit: Any, report: Any, unknown_sector_count: int) -> None:
    columns = streamlit.columns(4)
    columns[0].markdown("**Review first**")
    columns[0].caption(_symbol_preview(report.near_breakout_candidates) or "No near-trigger candidates.")
    columns[1].markdown("**Improving**")
    columns[1].caption(_symbol_preview(report.improving_candidates) or "No score improvers.")
    columns[2].markdown("**Avoid chasing**")
    columns[2].caption(_symbol_preview(report.extended_leaders) or "No extended leaders in this report.")
    columns[3].markdown("**Data cleanup**")
    columns[3].caption(
        f"{unknown_sector_count} missing sector rows."
        if unknown_sector_count
        else "Sector metadata is complete for this list."
    )


def _diagnostics_section(
    streamlit: Any,
    title: str,
    candidates: list[ScanCandidate],
    metadata_store: SymbolMetadataStore,
) -> None:
    frame = morning_report_frame(candidates, metadata_store)
    diagnostics = _candidate_diagnostics_frame(frame)
    with streamlit.expander(title):
        if diagnostics.empty:
            streamlit.info("No diagnostics available.")
        else:
            streamlit.dataframe(diagnostics, width="stretch", hide_index=True)


def _candidate_display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "quality",
        "status",
        "sector",
        "rank_score",
        "setup_score",
        "weekly_status",
        "distance_to_resistance",
        "range_pct",
        "relative_volume_20d",
    ]
    display = frame[[column for column in columns if column in frame.columns]].copy()
    for column in ["rank_score", "setup_score"]:
        if column in display:
            display[column] = display[column].map(lambda value: f"{float(value):.2f}")
    for column in ["distance_to_resistance", "range_pct"]:
        if column in display:
            display[column] = display[column].map(lambda value: f"{float(value):.1%}")
    if "relative_volume_20d" in display:
        display["relative_volume_20d"] = display["relative_volume_20d"].map(lambda value: f"{float(value):.2f}x")
    if "missing" in display:
        display["missing"] = display["missing"].replace("", "None")
    return display.rename(
        columns={
            "symbol": "Symbol",
            "quality": "Quality",
            "status": "Status",
            "sector": "Sector",
            "rank_score": "Rank",
            "setup_score": "Setup",
            "weekly_status": "Weekly",
            "distance_to_resistance": "To Resistance",
            "range_pct": "Range",
            "relative_volume_20d": "RVOL 20D",
        }
    )


def _candidate_diagnostics_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "sector",
        "industry",
        "relative_volume_20d",
        "missing",
    ]
    display = frame[[column for column in columns if column in frame.columns]].copy()
    if display.empty:
        return display
    if "relative_volume_20d" in display:
        display["relative_volume_20d"] = display["relative_volume_20d"].map(lambda value: f"{float(value):.2f}x")
    if "missing" in display:
        display["missing"] = display["missing"].replace("", "None")
    return display.rename(
        columns={
            "symbol": "Symbol",
            "sector": "Sector",
            "industry": "Industry",
            "relative_volume_20d": "RVOL 20D",
            "missing": "Missing Rules",
        }
    )


def _sector_display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    if "sector" in display:
        display["_is_unknown"] = display["sector"].fillna("Unknown").astype(str).str.lower().eq("unknown")
        display = display.sort_values(["_is_unknown", "avg_rank_score", "candidates"], ascending=[True, False, False])
        display = display.drop(columns=["_is_unknown"])
    for column in ["avg_rank_score", "avg_setup_score"]:
        if column in display:
            display[column] = display[column].map(lambda value: f"{float(value):.2f}")
    return display.rename(
        columns={
            "sector": "Sector",
            "candidates": "Candidates",
            "avg_rank_score": "Avg Rank",
            "avg_setup_score": "Avg Setup",
            "near_breakout": "Near Breakout",
            "extended": "Extended",
        }
    )


def _format_run_time(value: str, timezone: str = "America/New_York") -> str:
    return format_timestamp(value, timezone=timezone)


def _unknown_sector_count(candidates: list[ScanCandidate], metadata_store: SymbolMetadataStore) -> int:
    frame = morning_report_frame(candidates, metadata_store)
    if frame.empty or "sector" not in frame:
        return 0
    sectors = frame["sector"].fillna("Unknown").astype(str).str.strip().str.lower()
    return int(sectors.eq("unknown").sum())


def _symbol_preview(candidates: list[ScanCandidate], limit: int = 5) -> str:
    symbols = [candidate.symbol for candidate in candidates[:limit]]
    suffix = "..." if len(candidates) > limit else ""
    return ", ".join(symbols) + suffix if symbols else ""


run_standalone_page(
    "Morning Report",
    "Turn the latest saved scan into watchlist buckets for review.",
    render_morning_report_page,
)
