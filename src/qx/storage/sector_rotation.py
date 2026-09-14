import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qx.market.sector_rotation import SectorRotationResult
from qx.storage.connection import connect_sqlite


@dataclass(frozen=True)
class StoredSectorRotationSnapshot:
    id: int
    created_at: str
    source: str
    period: str
    data_source: str
    leaders: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class SectorRankChange:
    sector: str
    current_rank: int
    previous_rank: int | None
    rank_change: int | None
    current_status: str
    previous_status: str | None
    current_score: float
    previous_score: float | None


class SQLiteSectorRotationRepository:
    """Stores sector rotation snapshots for week/month rank-change review."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sector_rotation_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    period TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    leaders TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(
        self,
        result: SectorRotationResult,
        *,
        source: str,
        period: str,
        data_source: str,
        extras: dict[str, Any] | None = None,
    ) -> int:
        self.initialize()
        payload = {
            "benchmark": result.benchmark,
            "sectors": [asdict(row) for row in result.rows],
            "failures": result.failures,
            "extras": extras or {},
        }
        with connect_sqlite(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO sector_rotation_snapshots
                    (created_at, source, period, data_source, leaders, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    source,
                    period,
                    data_source,
                    ",".join(row.sector for row in result.leaders),
                    json.dumps(payload),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a sector rotation snapshot id")
            return int(cursor.lastrowid)

    def latest(self) -> StoredSectorRotationSnapshot | None:
        snapshots = self.list_snapshots(limit=1)
        return snapshots[0] if snapshots else None

    def list_snapshots(self, limit: int = 10) -> list[StoredSectorRotationSnapshot]:
        self.initialize()
        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, source, period, data_source, leaders, payload_json
                FROM sector_rotation_snapshots
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_snapshot(row) for row in rows]

    def compare_latest(self) -> list[SectorRankChange]:
        snapshots = self.list_snapshots(limit=2)
        if len(snapshots) < 2:
            return []
        current, previous_snapshot = snapshots
        # Configuration changes are not evidence of market rotation.
        if (current.period != previous_snapshot.period
                or current.data_source != previous_snapshot.data_source
                or current.payload.get("benchmark") != previous_snapshot.payload.get("benchmark")
                or not current.payload.get("benchmark")):
            return []
        current_rows = _sector_rows(current)
        prior_rows = _sector_rows(previous_snapshot)
        current_names = {str(row.get("sector", "")) for row in current_rows}
        prior_names = {str(row.get("sector", "")) for row in prior_rows}
        if (current_names != prior_names or "" in current_names
                or len(current_names) != len(current_rows)
                or len(prior_names) != len(prior_rows)):
            return []
        previous_rows = _sector_rows_by_name(previous_snapshot)
        changes = []
        for rank, row in enumerate(current_rows, start=1):
            sector = str(row["sector"])
            previous = previous_rows.get(sector)
            previous_rank = previous[0] if previous else None
            rank_change = previous_rank - rank if previous_rank is not None else None
            changes.append(
                SectorRankChange(
                    sector=sector,
                    current_rank=rank,
                    previous_rank=previous_rank,
                    rank_change=rank_change,
                    current_status=str(row.get("rotation_status", "")),
                    previous_status=str(previous[1].get("rotation_status", "")) if previous else None,
                    current_score=float(row.get("leadership_score", 0.0) or 0.0),
                    previous_score=float(previous[1].get("leadership_score", 0.0) or 0.0) if previous else None,
                )
            )
        return changes


def _row_to_snapshot(row: tuple[object, ...]) -> StoredSectorRotationSnapshot:
    return StoredSectorRotationSnapshot(
        id=int(str(row[0])),
        created_at=str(row[1]),
        source=str(row[2]),
        period=str(row[3]),
        data_source=str(row[4]),
        leaders=str(row[5]),
        payload=dict(json.loads(str(row[6]))),
    )


def _sector_rows(snapshot: StoredSectorRotationSnapshot) -> list[dict[str, Any]]:
    sectors = snapshot.payload.get("sectors", [])
    if not isinstance(sectors, list):
        return []
    return [dict(row) for row in sectors if isinstance(row, dict)]


def _sector_rows_by_name(snapshot: StoredSectorRotationSnapshot) -> dict[str, tuple[int, dict[str, Any]]]:
    return {
        str(row["sector"]): (rank, row)
        for rank, row in enumerate(_sector_rows(snapshot), start=1)
        if row.get("sector")
    }
