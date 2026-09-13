"""Lightweight Signal & Decision Telemetry Service (Section 23)."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid
from pydantic import BaseModel, Field


class SignalTelemetryRecord(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str
    underlying_price: float
    market_regime: str = "NEUTRAL"
    direction_score: float
    volatility_score: float
    qx_score: float
    recommended_strategy: str
    scoring_version: str = "1.0.0"
    config_version: str = "1.0.0"
    max_risk_dollars: float
    quality_grade: str = "B"
    final_outcome: str | None = None
    realized_pnl: float | None = None


class TelemetryService:
    def __init__(self, log_dir: Path = Path("data/telemetry")):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "signal_records.jsonl"

    def record_signal(self, record: SignalTelemetryRecord) -> str:
        """Persist a lightweight signal telemetry record as a JSONL entry."""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        return record.signal_id

    def list_records(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent signal records."""
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
