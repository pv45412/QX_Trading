from pathlib import Path

from qx.automation import morning


def test_log_tail_handles_missing_file(tmp_path: Path) -> None:
    assert morning.read_log_tail(tmp_path / "missing.log") == "Log file does not exist yet."


def test_log_file_status_identifies_empty_and_missing_logs(tmp_path: Path) -> None:
    missing = morning.log_file_status(tmp_path / "missing.log")
    empty_log = tmp_path / "empty.log"
    empty_log.write_text("", encoding="utf-8")

    status = morning.log_file_status(empty_log)

    assert not missing.exists
    assert missing.empty
    assert status.exists
    assert status.empty
    assert status.size_bytes == 0


def test_log_tail_returns_last_lines(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text("\n".join([f"line {index}" for index in range(10)]), encoding="utf-8")

    assert morning.read_log_tail(log, max_lines=3) == "line 7\nline 8\nline 9"


def test_log_tail_decodes_utf16_powershell_logs(tmp_path: Path) -> None:
    log = tmp_path / "powershell.log"
    log.write_text("Overnight workflow complete\nRegime: Risk On", encoding="utf-16")

    assert morning.read_log_tail(log, max_lines=2) == "Overnight workflow complete\nRegime: Risk On"


def test_missing_script_result_is_safe(tmp_path: Path) -> None:
    result = morning._run_script(tmp_path / "missing.ps1", tmp_path / "missing.log", timeout_seconds=1)

    assert not result.ok
    assert result.exit_code == 1
    assert "Script not found" in result.output


def test_task_result_label_explains_common_windows_codes() -> None:
    assert morning._task_result_label("0") == "Success"
    assert morning._task_result_label("3221225786") == "Interrupted / terminated"
    assert morning._task_result_label("1") == "Failed (1)"
