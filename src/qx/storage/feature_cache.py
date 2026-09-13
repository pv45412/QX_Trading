import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from qx.models.scan import RectangleScanParameters, ScanCandidate

FEATURE_CACHE_VERSION = "rectangle-v5-valid-proximity"


@dataclass(frozen=True)
class FeatureCacheKey:
    symbol: str
    period: str
    last_bar_date: str
    parameter_hash: str


class SQLiteFeatureCache:
    """Stores deterministic pattern-analysis outputs keyed by symbol/date/profile."""

    def __init__(self, database_path: Path = Path("data/feature_cache.db")) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rectangle_features (
                    symbol TEXT NOT NULL,
                    period TEXT NOT NULL,
                    last_bar_date TEXT NOT NULL,
                    parameter_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    PRIMARY KEY (symbol, period, last_bar_date, parameter_hash)
                )
                """
            )

    def get(self, key: FeatureCacheKey) -> ScanCandidate | None:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT candidate_json
                FROM rectangle_features
                WHERE symbol = ?
                  AND period = ?
                  AND last_bar_date = ?
                  AND parameter_hash = ?
                """,
                (key.symbol, key.period, key.last_bar_date, key.parameter_hash),
            ).fetchone()
        if row is None:
            return None
        return ScanCandidate.model_validate_json(str(row[0]))

    def set(self, key: FeatureCacheKey, candidate: ScanCandidate) -> None:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO rectangle_features
                    (symbol, period, last_bar_date, parameter_hash, created_at, candidate_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key.symbol,
                    key.period,
                    key.last_bar_date,
                    key.parameter_hash,
                    datetime.now(UTC).isoformat(),
                    candidate.model_dump_json(),
                ),
            )

    def count(self) -> int:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM rectangle_features").fetchone()
        return int(row[0]) if row else 0


def build_feature_cache_key(
    symbol: str,
    bars: pd.DataFrame,
    parameters: RectangleScanParameters,
    *,
    period: str,
) -> FeatureCacheKey:
    if bars.empty:
        raise ValueError("Cannot build feature cache key for empty bars")
    last_index = bars.index[-1]
    last_bar_date = pd.Timestamp(last_index).date().isoformat()
    # Indicators use the entire history, not just the box or latest candle.
    history = bars[["open", "high", "low", "close", "volume"]].astype(float)
    history_hash = hashlib.sha256(pd.util.hash_pandas_object(history, index=True).to_numpy().tobytes()).hexdigest()
    parameter_payload = json.dumps(
        {
            "cache_version": FEATURE_CACHE_VERSION,
            "history_hash": history_hash,
            "parameters": parameters.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    parameter_hash = hashlib.sha256(parameter_payload.encode("utf-8")).hexdigest()[:16]
    return FeatureCacheKey(
        symbol=symbol.strip().upper(),
        period=period,
        last_bar_date=last_bar_date,
        parameter_hash=parameter_hash,
    )
