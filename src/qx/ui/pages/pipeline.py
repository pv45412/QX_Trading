from pathlib import Path
from typing import Any

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.config.settings import get_settings
from qx.data.factory import build_fallback_market_data_provider
from qx.data.universe import UNIVERSE_OPTIONS
from qx.market.sector_rotation import sector_rotation_frame
from qx.patterns.profiles import PROFILE_OPTIONS
from qx.processing.overnight_workflow import OvernightWorkflowResult, run_overnight_workflow
from qx.reports.morning import morning_report_frame
from qx.storage.pipeline import PipelineRunMetadata, SQLitePipelineRepository, pipeline_runs_frame
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame, format_timestamp
from qx.ui.metadata import displayed_candidate_metadata


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_pipeline_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    universe_label = streamlit.sidebar.selectbox(
        "Pipeline universe",
        ["All", *UNIVERSE_OPTIONS.keys()],
        index=5,
    )
    period = streamlit.sidebar.selectbox("Pipeline history", ["2y", "3y", "5y"], index=0)
    data_source = streamlit.sidebar.selectbox(
        "Pipeline data source",
        MARKET_DATA_PROVIDER_OPTIONS,
        index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
    )
    profile = streamlit.sidebar.selectbox("Pipeline profile", PROFILE_OPTIONS, index=1)
    lookback = streamlit.sidebar.slider("Pattern bars", 30, 60, 40, 5)
    max_range_pct = streamlit.sidebar.slider("Max range %", 0.05, 0.25, 0.25, 0.01)
    refresh = streamlit.sidebar.checkbox("Force data refresh", value=False)

    streamlit.subheader("Pipeline Control")
    streamlit.caption(
        "One-button run: token check -> data cache -> scanner -> daily workflow -> saved history."
    )
    repository = SQLitePipelineRepository(SCAN_HISTORY_DB)
    _render_recent_pipeline_runs(streamlit, repository)

    if not streamlit.button("Run full pipeline", type="primary"):
        streamlit.info("Use this after-hours or before the session to prepare the next trading plan.")
        return

    universe = "all" if str(universe_label).lower() == "all" else UNIVERSE_OPTIONS[str(universe_label)]
    metadata = PipelineRunMetadata(
        universe=universe,
        period=str(period),
        profile=str(profile),
        data_source=str(data_source),
        lookback=int(lookback),
        max_range_pct=float(max_range_pct),
        refresh=bool(refresh),
    )
    with streamlit.spinner("Running full QuantX pipeline..."):
        result = run_overnight_workflow(
            provider=build_fallback_market_data_provider(str(data_source)),
            universe=metadata.universe,
            period=metadata.period,
            profile=metadata.profile,
            lookback=metadata.lookback,
            max_range_pct=metadata.max_range_pct,
            refresh=metadata.refresh,
            database=SCAN_HISTORY_DB,
            token_manager=SchwabTokenManager(get_settings()),
        )

    pipeline_run_id = repository.save(result, metadata)
    _render_pipeline_result(streamlit, result, pipeline_run_id)


def _render_recent_pipeline_runs(streamlit: Any, repository: SQLitePipelineRepository) -> None:
    runs = repository.list_runs(limit=10)
    if not runs:
        streamlit.info("No saved pipeline runs yet.")
        return

    latest = runs[0]
    issue_count = int(latest.cache_failures) + int(latest.scan_failures)
    metrics = streamlit.columns(7)
    metrics[0].metric("Last Run", format_timestamp(latest.created_at))
    metrics[1].metric("Health", _pipeline_health_label(latest))
    metrics[2].metric("Cached", latest.cached_symbols)
    metrics[3].metric("Scanned", latest.scanned_symbols)
    metrics[4].metric("Candidates", latest.candidates)
    metrics[5].metric("Cache Failures", latest.cache_failures)
    metrics[6].metric("Scan Failures", latest.scan_failures)
    if issue_count:
        streamlit.warning(
            f"Latest pipeline has {issue_count} data issue(s): "
            f"{latest.cache_failures} cache failure(s), {latest.scan_failures} scan failure(s)."
        )

    with streamlit.container(border=True):
        streamlit.markdown("**Pipeline Readout**")
        render_bullet_list(streamlit, _pipeline_action_items(latest))

    with streamlit.expander("Recent Pipeline Runs", expanded=True):
        streamlit.dataframe(
            display_frame(pipeline_runs_frame(runs)),
            width="stretch",
            hide_index=True,
        )
    with streamlit.expander("Latest Pipeline Payload"):
        streamlit.json(latest.payload)


def _pipeline_health_label(run: Any) -> str:
    if getattr(run, "auth_warning", ""):
        return "Auth Warning"
    if getattr(run, "cache_failures", 0) or getattr(run, "scan_failures", 0):
        return "Data Issues"
    if getattr(run, "candidates", 0) == 0:
        return "No Candidates"
    return "Ready"


def _pipeline_action_items(run: Any) -> list[str]:
    if getattr(run, "auth_warning", ""):
        return [
            "Open Schwab API and refresh authorization before trusting live Schwab-backed scans.",
            "Run Schwab health check after saving a fresh token.",
            "Use cached results only as a fallback until auth is healthy.",
        ]
    if getattr(run, "cache_failures", 0) or getattr(run, "scan_failures", 0):
        issue_count = int(getattr(run, "cache_failures", 0)) + int(getattr(run, "scan_failures", 0))
        return [
            f"Review data issues from the latest pipeline run: {issue_count} cache/scan failure(s).",
            "Prefer cached S&P 500 or a smaller universe until failed symbols are cleaned up.",
            "If failures are mostly delisted symbols, refresh universe membership before the next run.",
        ]
    if getattr(run, "candidates", 0) == 0:
        return [
            "Pipeline is technically healthy, but no candidates were produced.",
            "Review rule profile, minimum score, and max range settings before loosening scanner logic.",
        ]
    return [
        "Pipeline is ready for morning review.",
        "Use Command Center latest snapshot first; refresh live only when you need intraday context.",
    ]


def _render_pipeline_result(
    streamlit: Any,
    result: OvernightWorkflowResult,
    pipeline_run_id: int,
) -> None:
    if result.auth_warning:
        streamlit.warning(f"Schwab auth warning: {result.auth_warning}")

    streamlit.success(
        f"Pipeline run {pipeline_run_id} complete. "
        f"Scan run {result.scan_run_id}; workflow run {result.workflow_run_id}."
    )

    metrics = streamlit.columns(5)
    metrics[0].metric("Cached", result.cache_refresh.refreshed_symbols)
    metrics[1].metric("Cache Failures", result.cache_refresh.failed_symbols)
    metrics[2].metric("Scanned", result.scan_result.total_symbols)
    metrics[3].metric("Candidates", len(result.scan_result.candidates))
    metrics[4].metric("Data Failures", result.scan_result.failed_symbols)

    streamlit.subheader("Market Regime")
    regime_cols = streamlit.columns(4)
    regime_cols[0].metric("Regime", result.workflow_report.regime.label)
    regime_cols[1].metric("Risk", result.workflow_report.regime.risk_level)
    regime_cols[2].metric("SPY 20D", f"{result.workflow_report.regime.spy_return_20d:.1%}")
    regime_cols[3].metric("Realized Vol", f"{result.workflow_report.regime.realized_vol_20d:.1%}")

    streamlit.subheader("Action Plan")
    render_bullet_list(streamlit, result.workflow_report.action_plan)

    streamlit.subheader("Sector Leadership")
    streamlit.dataframe(
        display_frame(sector_rotation_frame(result.workflow_report.sector_rotation)),
        width="stretch",
        hide_index=True,
    )

    streamlit.subheader("Top Watchlist")
    metadata_store, _ = displayed_candidate_metadata(
        result.workflow_report.morning_report.top_candidates,
        max_symbols=min(len(result.workflow_report.morning_report.top_candidates), 50),
    )
    streamlit.dataframe(
        display_frame(morning_report_frame(result.workflow_report.morning_report.top_candidates, metadata_store)),
        width="stretch",
        hide_index=True,
    )

    if result.cache_refresh.failures:
        with streamlit.expander("Cache failures"):
            streamlit.json([failure.__dict__ for failure in result.cache_refresh.failures[:50]])


run_standalone_page(
    "Pipeline Control",
    "Run data cache, scanner, workflow, and history persistence in one pass.",
    render_pipeline_page,
)
