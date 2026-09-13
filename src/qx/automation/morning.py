import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


TASK_NAME = "SCANNER Overnight Workflow"


@dataclass(frozen=True)
class AutomationTaskStatus:
    exists: bool
    task_name: str
    state: str
    last_run_time: str
    next_run_time: str
    last_task_result: str
    last_task_result_label: str
    message: str


@dataclass(frozen=True)
class AutomationRunResult:
    exit_code: int
    output: str
    log_path: Path

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class LogFileStatus:
    path: Path
    exists: bool
    last_write_time: str
    size_bytes: int
    empty: bool


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def morning_snapshot_log_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "logs" / "morning_snapshot.log"


def overnight_log_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "logs" / "overnight_workflow.log"


def schedule_script_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "scripts" / "schedule_overnight_workflow.ps1"


def morning_snapshot_script_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "scripts" / "run_morning_snapshot.ps1"


def overnight_script_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "scripts" / "run_overnight_workflow.ps1"


def get_task_status(task_name: str = TASK_NAME) -> AutomationTaskStatus:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            f"$task = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue; "
            "if ($null -eq $task) { Write-Output 'MISSING' } "
            "else { "
            f"$info = Get-ScheduledTaskInfo -TaskName '{task_name}'; "
            "Write-Output ($task.State.ToString() + '|' + $info.LastRunTime + '|' + "
            "$info.NextRunTime + '|' + $info.LastTaskResult) "
            "}"
        ),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return AutomationTaskStatus(
            exists=False,
            task_name=task_name,
            state="Unknown",
            last_run_time="",
            next_run_time="",
            last_task_result=str(result.returncode),
            last_task_result_label=_task_result_label(str(result.returncode)),
            message=output or "Could not inspect scheduled task.",
        )
    if output == "MISSING":
        return AutomationTaskStatus(
            exists=False,
            task_name=task_name,
            state="Missing",
            last_run_time="",
            next_run_time="",
            last_task_result="",
            last_task_result_label="Missing",
            message="Scheduled task has not been created yet.",
        )
    parts = output.split("|")
    return AutomationTaskStatus(
        exists=True,
        task_name=task_name,
        state=parts[0] if len(parts) > 0 else "Unknown",
        last_run_time=parts[1] if len(parts) > 1 else "",
        next_run_time=parts[2] if len(parts) > 2 else "",
        last_task_result=parts[3] if len(parts) > 3 else "",
        last_task_result_label=_task_result_label(parts[3] if len(parts) > 3 else ""),
        message="Scheduled task is configured.",
    )


def create_or_update_schedule(root: Path | None = None) -> AutomationRunResult:
    script = schedule_script_path(root)
    return _run_script(script, overnight_log_path(root), timeout_seconds=60)


def run_morning_snapshot_now(root: Path | None = None, *, timeout_seconds: int = 900) -> AutomationRunResult:
    script = morning_snapshot_script_path(root)
    return _run_script(script, morning_snapshot_log_path(root), timeout_seconds=timeout_seconds)


def run_overnight_workflow_now(root: Path | None = None, *, timeout_seconds: int = 1800) -> AutomationRunResult:
    script = overnight_script_path(root)
    return _run_script(script, overnight_log_path(root), timeout_seconds=timeout_seconds)


def log_file_status(path: Path) -> LogFileStatus:
    if not path.exists():
        return LogFileStatus(path=path, exists=False, last_write_time="", size_bytes=0, empty=True)
    stat = path.stat()
    return LogFileStatus(
        path=path,
        exists=True,
        last_write_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        size_bytes=stat.st_size,
        empty=stat.st_size == 0,
    )


def read_log_tail(path: Path, *, max_lines: int = 200) -> str:
    if not path.exists():
        return "Log file does not exist yet."
    lines = _read_log_text(path).splitlines()
    return "\n".join(lines[-max_lines:])


def _read_log_text(path: Path) -> str:
    data = path.read_bytes()
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:200]:
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


def _run_script(script: Path, log_path: Path, *, timeout_seconds: int) -> AutomationRunResult:
    if not script.exists():
        return AutomationRunResult(
            exit_code=1,
            output=f"Script not found: {script}",
            log_path=log_path,
        )
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=project_root(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_output = exc.stdout or exc.stderr or "Command timed out."
        if isinstance(timeout_output, bytes):
            timeout_output = timeout_output.decode("utf-8", errors="replace")
        return AutomationRunResult(
            exit_code=124,
            output=timeout_output.strip(),
            log_path=log_path,
        )
    return AutomationRunResult(
        exit_code=result.returncode,
        output=((result.stdout or "") + (result.stderr or "")).strip(),
        log_path=log_path,
    )


def _task_result_label(value: str) -> str:
    normalized = value.strip()
    if normalized in {"", "0"}:
        return "Success" if normalized == "0" else "Unknown"
    try:
        numeric = int(normalized)
    except ValueError:
        return normalized
    if numeric == 0:
        return "Success"
    if numeric == 3221225786:
        return "Interrupted / terminated"
    return f"Failed ({numeric})"
