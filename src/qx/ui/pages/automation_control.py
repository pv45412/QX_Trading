from typing import Any

from qx.automation.morning import (
    create_or_update_schedule,
    get_task_status,
    log_file_status,
    morning_snapshot_log_path,
    overnight_log_path,
    project_root,
    read_log_tail,
    run_morning_snapshot_now,
    run_overnight_workflow_now,
)
from qx.storage.command_center import SQLiteCommandCenterSnapshotRepository, snapshot_freshness_label
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.status import friendly_iso_time, log_size_label


def render_automation_control_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.subheader("Automation Control")
    streamlit.caption("Run and monitor the local morning snapshot workflow from the app.")

    status = get_task_status()
    _render_task_status(streamlit, status)

    cols = streamlit.columns(4)
    if cols[0].button("Run morning snapshot now", type="primary"):
        with streamlit.spinner("Running morning snapshot. This can take several minutes..."):
            result = run_morning_snapshot_now()
        if result.ok:
            streamlit.success(f"Morning snapshot completed. Log: {result.log_path}")
        else:
            streamlit.error(f"Morning snapshot failed with exit code {result.exit_code}.")
        if result.output:
            with streamlit.expander("Command output", expanded=not result.ok):
                streamlit.code(result.output)

    if cols[1].button("Run overnight workflow now"):
        with streamlit.spinner("Running overnight workflow. This can take several minutes..."):
            result = run_overnight_workflow_now()
        if result.ok:
            streamlit.success(f"Overnight workflow completed. Log: {result.log_path}")
        else:
            streamlit.error(f"Overnight workflow failed with exit code {result.exit_code}.")
        if result.output:
            with streamlit.expander("Command output", expanded=not result.ok):
                streamlit.code(result.output)

    if cols[2].button("Create/update 4:30 AM task"):
        result = create_or_update_schedule()
        if result.ok:
            streamlit.success("Scheduled task created or updated for 4:30 AM.")
        else:
            streamlit.error(f"Could not create scheduled task. Exit code {result.exit_code}.")
        if result.output:
            with streamlit.expander("Scheduler output", expanded=not result.ok):
                streamlit.code(result.output)

    if cols[3].button("Refresh task status"):
        streamlit.rerun()

    _render_latest_snapshot(streamlit)
    _render_logs(streamlit)


def _render_task_status(streamlit: Any, status: Any) -> None:
    cols = streamlit.columns(5)
    cols[0].metric("Task", "Configured" if status.exists else "Missing")
    cols[1].metric("State", status.state)
    cols[2].metric("Last Run", friendly_iso_time(status.last_run_time))
    cols[3].metric("Next Run", friendly_iso_time(status.next_run_time))
    cols[4].metric("Last Result", status.last_task_result_label or status.last_task_result or "n/a")
    if status.exists:
        if status.last_task_result in {"", "0"}:
            streamlit.success(status.message)
        else:
            streamlit.warning(f"{status.message} Last run result: {status.last_task_result_label}.")
    else:
        streamlit.warning(status.message)


def _render_latest_snapshot(streamlit: Any) -> None:
    latest = SQLiteCommandCenterSnapshotRepository(project_root() / "data" / "scanner_history.db").latest()
    streamlit.subheader("Latest Command Snapshot")
    if latest is None:
        streamlit.info("No Command Center snapshot exists yet.")
        return
    streamlit.write(snapshot_freshness_label(latest))
    cols = streamlit.columns(5)
    cols[0].metric("Regime", latest.regime_label)
    cols[1].metric("Risk", latest.risk_level)
    cols[2].metric("SPX Bias", latest.spx_bias)
    cols[3].metric("Watchlist", latest.watchlist_count)
    cols[4].metric("Options", latest.option_ideas_count)


def _render_logs(streamlit: Any) -> None:
    streamlit.subheader("Logs")
    selected_log = streamlit.selectbox(
        "Log file",
        ["morning_snapshot.log", "overnight_workflow.log"],
        index=0,
    )
    log_path = morning_snapshot_log_path() if selected_log == "morning_snapshot.log" else overnight_log_path()
    max_lines = streamlit.slider("Log lines", 25, 500, 100, 25)
    status = log_file_status(log_path)
    cols = streamlit.columns(3)
    cols[0].metric("Exists", "Yes" if status.exists else "No")
    cols[1].metric("Size", log_size_label(status))
    cols[2].metric("Updated", friendly_iso_time(status.last_write_time))
    if status.empty:
        streamlit.warning("This log is empty. The workflow may not have completed or may not have written output.")
    streamlit.caption(str(log_path))
    streamlit.code(read_log_tail(log_path, max_lines=int(max_lines)))


run_standalone_page(
    "Automation Control",
    "Run, schedule, and monitor local morning snapshot automation.",
    render_automation_control_page,
)
