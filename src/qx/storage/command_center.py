import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from qx.reports.command_center import CommandCenter
from qx.storage.connection import connect_sqlite


@dataclass(frozen=True)
class CommandCenterSnapshotMetadata:
    source: str
    period: str
    data_source: str
    universe: str


@dataclass(frozen=True)
class StoredCommandCenterSnapshot:
    id: int
    created_at: str
    source: str
    period: str
    data_source: str
    universe: str
    regime_label: str
    risk_level: str
    spx_bias: str
    volatility_context: str
    watchlist_count: int
    option_ideas_count: int
    saved_options_count: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class CommandCenterSnapshotComparison:
    current: StoredCommandCenterSnapshot | None
    previous: StoredCommandCenterSnapshot | None
    regime_changed: bool
    risk_changed: bool
    spx_bias_changed: bool
    new_watchlist_symbols: list[str]
    removed_watchlist_symbols: list[str]
    new_option_symbols: list[str]
    removed_option_symbols: list[str]
    new_top_sectors: list[str]
    removed_top_sectors: list[str]


class SQLiteCommandCenterSnapshotRepository:
    """Stores complete morning Command Center snapshots for fast local startup."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS command_center_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    period TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    universe TEXT NOT NULL,
                    regime_label TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    spx_bias TEXT NOT NULL,
                    volatility_context TEXT NOT NULL,
                    watchlist_count INTEGER NOT NULL,
                    option_ideas_count INTEGER NOT NULL,
                    saved_options_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(
        self,
        center: CommandCenter,
        metadata: CommandCenterSnapshotMetadata,
    ) -> int:
        self.initialize()
        payload = command_center_payload(center, metadata)
        created_at = datetime.now(UTC).isoformat()
        option_ideas_count = len(center.option_ideas) + len(center.directional_option_ideas)
        with connect_sqlite(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO command_center_snapshots (
                    created_at, source, period, data_source, universe,
                    regime_label, risk_level, spx_bias, volatility_context,
                    watchlist_count, option_ideas_count, saved_options_count, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    metadata.source,
                    metadata.period,
                    metadata.data_source,
                    metadata.universe,
                    center.workflow.regime.label,
                    center.workflow.regime.risk_level,
                    center.spx.trend_bias,
                    center.spx.volatility_context,
                    len(center.watchlist),
                    option_ideas_count,
                    len(center.saved_option_ideas),
                    json.dumps(payload),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a Command Center snapshot id")
            return int(cursor.lastrowid)

    def latest(self) -> StoredCommandCenterSnapshot | None:
        snapshots = self.list_snapshots(limit=1)
        return snapshots[0] if snapshots else None

    def list_snapshots(
        self, limit: int = 10, *, universes: tuple[str, ...] = (), period: str | None = None,
        data_source: str | None = None, snapshot_id: int | None = None,
        created_before: str | None = None, before_id: int | None = None,
    ) -> list[StoredCommandCenterSnapshot]:
        self.initialize()
        clauses: list[str] = []
        values: list[str | int] = []
        if universes:
            clauses.append("universe IN (" + ",".join("?" for _ in universes) + ")")
            values.extend(universes)
        for column, value in (("period", period), ("data_source", data_source), ("id", snapshot_id)):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        if created_before is not None:
            clauses.append("julianday(created_at) < julianday(?)")
            values.append(created_before)
        if before_id is not None:
            clauses.append("id < ?")
            values.append(before_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id, created_at, source, period, data_source, universe,
                    regime_label, risk_level, spx_bias, volatility_context,
                    watchlist_count, option_ideas_count, saved_options_count, payload_json
                FROM command_center_snapshots
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*values, limit),
            ).fetchall()
        return [_row_to_snapshot(row) for row in rows]

    def compare_latest(self) -> CommandCenterSnapshotComparison:
        snapshots = self.list_snapshots(limit=2)
        current = snapshots[0] if snapshots else None
        previous = snapshots[1] if len(snapshots) > 1 else None
        if current is None or previous is None:
            return CommandCenterSnapshotComparison(
                current=current,
                previous=previous,
                regime_changed=False,
                risk_changed=False,
                spx_bias_changed=False,
                new_watchlist_symbols=[],
                removed_watchlist_symbols=[],
                new_option_symbols=[],
                removed_option_symbols=[],
                new_top_sectors=[],
                removed_top_sectors=[],
            )

        current_watchlist = _symbols_from_rows(current.payload.get("watchlist", []))
        previous_watchlist = _symbols_from_rows(previous.payload.get("watchlist", []))
        current_options = _option_symbols(current.payload.get("options", {}))
        previous_options = _option_symbols(previous.payload.get("options", {}))
        current_sectors = _sector_names(current.payload.get("sectors", []), limit=3)
        previous_sectors = _sector_names(previous.payload.get("sectors", []), limit=3)

        return CommandCenterSnapshotComparison(
            current=current,
            previous=previous,
            regime_changed=current.regime_label != previous.regime_label,
            risk_changed=current.risk_level != previous.risk_level,
            spx_bias_changed=current.spx_bias != previous.spx_bias,
            new_watchlist_symbols=sorted(current_watchlist - previous_watchlist),
            removed_watchlist_symbols=sorted(previous_watchlist - current_watchlist),
            new_option_symbols=sorted(current_options - previous_options),
            removed_option_symbols=sorted(previous_options - current_options),
            new_top_sectors=sorted(current_sectors - previous_sectors),
            removed_top_sectors=sorted(previous_sectors - current_sectors),
        )


def command_center_payload(
    center: CommandCenter,
    metadata: CommandCenterSnapshotMetadata,
) -> dict[str, Any]:
    return {
        "metadata": asdict(metadata),
        "market_state": {
            "regime": asdict(center.workflow.regime),
            "spx": asdict(center.spx),
        },
        "summary": {
            "regime_label": center.workflow.regime.label,
            "risk_level": center.workflow.regime.risk_level,
            "spx_bias": center.spx.trend_bias,
            "volatility_context": center.spx.volatility_context,
            "watchlist_count": len(center.watchlist),
            "option_ideas_count": len(center.option_ideas) + len(center.directional_option_ideas),
            "saved_options_count": len(center.saved_option_ideas),
        },
        "sectors": [asdict(row) for row in center.workflow.sector_rotation.rows],
        "sector_focus": center.sector_focus,
        "watchlist": [asdict(candidate) for candidate in center.watchlist],
        "rectangle_watchlist": [
            _scan_candidate_payload(candidate)
            for candidate in center.workflow.morning_report.top_candidates
        ],
        "options": {
            "rectangle_ideas": [asdict(idea) for idea in center.option_ideas],
            "directional_ideas": [asdict(idea) for idea in center.directional_option_ideas],
            "saved_ideas": [asdict(idea) for idea in center.saved_option_ideas],
        },
        "priorities": center.priorities,
        "action_plan": center.action_plan,
    }


def snapshot_is_stale(
    snapshot: StoredCommandCenterSnapshot,
    *,
    timezone: str = "America/New_York",
    premarket_time: time = time(4, 0),
) -> bool:
    created_at = _parse_snapshot_time(snapshot.created_at).astimezone(ZoneInfo(timezone))
    now = datetime.now(ZoneInfo(timezone))
    if created_at.date() < now.date():
        return True
    return created_at.date() == now.date() and created_at.time() < premarket_time


def snapshot_freshness_label(
    snapshot: StoredCommandCenterSnapshot,
    *,
    timezone: str = "America/New_York",
) -> str:
    created_at = _parse_snapshot_time(snapshot.created_at).astimezone(ZoneInfo(timezone))
    return (
        f"Snapshot {snapshot.id} from {created_at:%Y-%m-%d %I:%M %p %Z} "
        f"({snapshot.source}, {snapshot.universe}, {snapshot.data_source})"
    )


def _scan_candidate_payload(candidate: Any) -> dict[str, Any]:
    if hasattr(candidate, "model_dump"):
        return dict(candidate.model_dump(mode="json"))
    if hasattr(candidate, "__dict__"):
        return dict(candidate.__dict__)
    return {"value": str(candidate)}


def _parse_snapshot_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _symbols_from_rows(rows: object) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("symbol", "")).upper()
        for row in rows
        if isinstance(row, dict) and row.get("symbol")
    }


def _option_symbols(options: object) -> set[str]:
    if not isinstance(options, dict):
        return set()
    symbols: set[str] = set()
    for key in ["rectangle_ideas", "directional_ideas", "saved_ideas"]:
        symbols |= _symbols_from_rows(options.get(key, []))
    return symbols


def _sector_names(rows: object, *, limit: int) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("sector", ""))
        for row in rows[:limit]
        if isinstance(row, dict) and row.get("sector")
    }


def _row_to_snapshot(row: tuple[object, ...]) -> StoredCommandCenterSnapshot:
    return StoredCommandCenterSnapshot(
        id=int(str(row[0])),
        created_at=str(row[1]),
        source=str(row[2]),
        period=str(row[3]),
        data_source=str(row[4]),
        universe=str(row[5]),
        regime_label=str(row[6]),
        risk_level=str(row[7]),
        spx_bias=str(row[8]),
        volatility_context=str(row[9]),
        watchlist_count=int(str(row[10])),
        option_ideas_count=int(str(row[11])),
        saved_options_count=int(str(row[12])),
        payload=dict(json.loads(str(row[13]))),
    )
