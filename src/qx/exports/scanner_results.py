from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from qx.models.scan import ScanCandidate, ScanRunResult

SCANNER_RESULTS_COLUMNS = [
    "date",
    "ticker",
    "timeframe",
    "pattern",
    "status",
    "score",
    "multi_timeframe_score",
    "weekly_status",
    "support",
    "resistance",
    "entry",
    "stop",
    "target",
    "volume_confirmation",
    "notes",
]


def scanner_results_frame(
    candidates: list[ScanCandidate],
    *,
    scan_date: date | None = None,
    timeframe: str = "1D",
    pattern: str = "rectangle",
) -> pd.DataFrame:
    effective_date = scan_date or datetime.now(UTC).date()
    return pd.DataFrame(
        [_scanner_result_row(candidate, effective_date, timeframe, pattern) for candidate in candidates],
        columns=SCANNER_RESULTS_COLUMNS,
    )


qx_results_frame = scanner_results_frame


def write_scanner_results_csv(
    result: ScanRunResult,
    path: Path,
    *,
    timeframe: str = "1D",
    pattern: str = "rectangle",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scanner_results_frame(
        result.candidates,
        timeframe=timeframe,
        pattern=pattern,
    ).to_csv(path, index=False)


def _scanner_result_row(
    candidate: ScanCandidate,
    scan_date: date,
    timeframe: str,
    pattern: str,
) -> dict[str, object]:
    metrics = candidate.metrics
    target = metrics.breakout_level + (metrics.resistance - metrics.support)
    return {
        "date": scan_date.isoformat(),
        "ticker": candidate.symbol,
        "timeframe": timeframe,
        "pattern": pattern,
        "status": candidate.setup_status,
        "score": round(candidate.setup_score * 100, 1),
        "multi_timeframe_score": round(candidate.multi_timeframe_score * 100, 1),
        "weekly_status": candidate.weekly_context.status if candidate.weekly_context else "Unknown",
        "support": round(metrics.support, 2),
        "resistance": round(metrics.resistance, 2),
        "entry": round(metrics.breakout_level, 2),
        "stop": round(metrics.failure_level, 2),
        "target": round(target, 2),
        "volume_confirmation": round(metrics.relative_volume_20d, 3),
        "notes": _notes(candidate),
    }


def _notes(candidate: ScanCandidate) -> str:
    missing = ", ".join(candidate.failed_rule_names[:5])
    if missing:
        return f"{candidate.display_status}; missing: {missing}"
    return candidate.display_status
