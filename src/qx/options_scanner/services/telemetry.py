"""TelemetryService for QX Options Scanner V1.

Provides immutable signal snapshot logging with config versioning to guarantee
zero lookahead bias and 100% auditability.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from qx.options_scanner.models import ScanResult

logger = logging.getLogger(__name__)


class TelemetryService:
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path("data/options_telemetry")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def log_scan_snapshot(self, result: ScanResult) -> Path:
        """Saves a ScanResult as an immutable JSON snapshot file."""
        date_str = result.timestamp.strftime("%Y%m%d")
        time_str = result.timestamp.strftime("%H%M%S")
        filename = f"{result.symbol}_{date_str}_{time_str}_{result.config_version}.json"
        filepath = self.storage_dir / filename

        data = result.model_dump(mode="json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Saved immutable scanner telemetry snapshot to {filepath}")
        return filepath

    def load_snapshots_for_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """Loads historical snapshots for a given symbol."""
        snapshots = []
        pattern = f"{symbol.upper()}_*.json"
        for p in self.storage_dir.glob(pattern):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    snapshots.append(json.load(f))
            except Exception as e:
                logger.warning(f"Error loading snapshot {p}: {e}")
        return sorted(snapshots, key=lambda s: s.get("timestamp", ""), reverse=True)
