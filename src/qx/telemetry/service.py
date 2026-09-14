"""TelemetryService persistence and query engine."""

import json
from pathlib import Path
from typing import Any, List
from qx.telemetry.models import SignalTelemetryRecord


class TelemetryService:
    """Persists and retrieves lightweight signal telemetry audit logs."""

    def __init__(self, log_dir: Path = Path("data/telemetry")):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "signal_records.jsonl"

    def record_signal(self, record: SignalTelemetryRecord) -> str:
        """Persist a lightweight signal telemetry record as a JSONL entry.

        :param record: SignalTelemetryRecord to log
        :return: Recorded signal_id UUID
        """
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        return record.signal_id

    def list_records(self, limit: int = 50) -> List[dict[str, Any]]:
        """Retrieve recent signal records.

        :param limit: Maximum number of recent records to return
        :return: List of record dictionary objects
        """
        if not self.log_file.exists():
            return []

        records = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        return records[-limit:]

    def calculate_calibrated_win_rate(self, symbol: str | None = None) -> dict[str, Any]:
        """Compute empirical win rate from recorded trade outcome telemetry.

        :param symbol: Optional ticker symbol filter
        :return: Dict containing sample size, empirical win rate %, and calibration status
        """
        records = self.list_records(limit=1000)
        filtered = [r for r in records if r.get("final_outcome") is not None]
        if symbol:
            filtered = [r for r in filtered if r.get("symbol") == symbol]
        if not filtered:
            return {"sample_size": 0, "empirical_win_rate_pct": 55.0, "calibrated": False}

        wins = sum(1 for r in filtered if str(r.get("final_outcome")).upper() in ("WIN", "PROFIT", "SUCCESS"))
        rate = round((wins / len(filtered)) * 100.0, 1)
        return {
            "sample_size": len(filtered),
            "empirical_win_rate_pct": rate,
            "calibrated": True,
        }
