"""Point-in-time persistence for canonical read-only provider snapshots."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from qx.options_expression.models import OptionsContext
from qx.pipeline.models import PIPELINE_VERSION
from qx.pipeline.point_in_time import aware_utc
from qx.pipeline.point_in_time import parse_timestamp
from qx.portfolio.models import AccountRiskContext
from qx.storage.connection import connect_sqlite


def internal_account_id(value: str) -> str:
    if value.startswith("qxacct_") and len(value) == 23:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"qxacct_{digest}"


def sanitize_account_snapshot(snapshot: AccountRiskContext) -> AccountRiskContext:
    return snapshot.model_copy(update={"account_id": internal_account_id(snapshot.account_id)})


class CanonicalSnapshotRepository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS option_chain_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    data_as_of TEXT NOT NULL,
                    retrieved_at TEXT,
                    freshness TEXT NOT NULL,
                    publication_state TEXT NOT NULL,
                    sync_status TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_option_chain_snapshot_visibility
                ON option_chain_snapshots(symbol, data_as_of DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    data_as_of TEXT NOT NULL,
                    retrieved_at TEXT,
                    freshness TEXT NOT NULL,
                    publication_state TEXT NOT NULL,
                    sync_status TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            _ensure_column(connection, "account_snapshots", "retrieved_at", "TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_account_snapshot_visibility
                ON account_snapshots(data_as_of DESC)
                """
            )

    def save_option_chain(self, snapshot: OptionsContext, created_at: datetime) -> int:
        self.initialize()
        created = aware_utc(created_at).isoformat()
        retrieved_at = parse_timestamp(snapshot.retrieved_at) or aware_utc(created_at)
        stored_snapshot = snapshot.model_copy(
            update={"retrieved_at": retrieved_at.isoformat()}
        )
        data_as_of = parse_timestamp(snapshot.data_as_of)
        if data_as_of is None:
            raise ValueError("Option snapshot requires a valid data_as_of timestamp")
        with connect_sqlite(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO option_chain_snapshots (
                    symbol, source, data_as_of, retrieved_at, freshness,
                    publication_state, sync_status, pipeline_version, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.underlying_symbol.upper(),
                    snapshot.source,
                    data_as_of.isoformat(),
                    retrieved_at.isoformat(),
                    snapshot.freshness,
                    snapshot.publication_state,
                    snapshot.sync_status,
                    PIPELINE_VERSION,
                    stored_snapshot.model_dump_json(),
                    created,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an option snapshot row id")
            return int(cursor.lastrowid)

    def save_account(self, snapshot: AccountRiskContext, created_at: datetime) -> int:
        safe_snapshot = sanitize_account_snapshot(snapshot)
        self.initialize()
        created = aware_utc(created_at).isoformat()
        retrieved_timestamp = aware_utc(safe_snapshot.retrieved_at or created_at)
        retrieved_at = retrieved_timestamp.isoformat()
        stored_snapshot = safe_snapshot.model_copy(
            update={"retrieved_at": retrieved_timestamp}
        )
        with connect_sqlite(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO account_snapshots (
                    account_id, source, data_as_of, retrieved_at, freshness, publication_state,
                    sync_status, pipeline_version, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_snapshot.account_id,
                    safe_snapshot.broker_provenance,
                    aware_utc(safe_snapshot.data_as_of).isoformat(),
                    retrieved_at,
                    safe_snapshot.freshness.value,
                    safe_snapshot.publication_state,
                    safe_snapshot.sync_status,
                    PIPELINE_VERSION,
                    stored_snapshot.model_dump_json(),
                    created,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an account snapshot row id")
            return int(cursor.lastrowid)

    def latest_option_chain(
        self,
        symbol: str,
        evaluation_timestamp: datetime,
    ) -> Optional[OptionsContext]:
        self.initialize()
        cutoff = aware_utc(evaluation_timestamp).isoformat()
        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, payload_json
                FROM option_chain_snapshots
                WHERE symbol = ? AND data_as_of <= ?
                  AND retrieved_at IS NOT NULL AND retrieved_at <= ?
                  AND created_at <= ?
                ORDER BY data_as_of DESC, id DESC
                LIMIT 1
                """,
                (symbol.upper(), cutoff, cutoff, cutoff),
            ).fetchone()
        return (
            OptionsContext.model_validate_json(row[1]).model_copy(
                update={"snapshot_id": int(row[0])}
            )
            if row is not None
            else None
        )

    def latest_account(self, evaluation_timestamp: datetime) -> Optional[AccountRiskContext]:
        self.initialize()
        cutoff = aware_utc(evaluation_timestamp).isoformat()
        with connect_sqlite(self.database_path) as connection:
            account_ids = connection.execute(
                """
                SELECT DISTINCT account_id
                FROM account_snapshots
                WHERE data_as_of <= ? AND retrieved_at IS NOT NULL
                  AND retrieved_at <= ? AND created_at <= ?
                """,
                (cutoff, cutoff, cutoff),
            ).fetchall()
            if len(account_ids) != 1:
                return None
            row = connection.execute(
                """
                SELECT id, payload_json
                FROM account_snapshots
                WHERE account_id = ? AND data_as_of <= ?
                  AND retrieved_at IS NOT NULL AND retrieved_at <= ?
                  AND created_at <= ?
                ORDER BY data_as_of DESC, id DESC
                LIMIT 1
                """,
                (account_ids[0][0], cutoff, cutoff, cutoff),
            ).fetchone()
        return (
            AccountRiskContext.model_validate_json(row[1]).model_copy(
                update={"snapshot_id": int(row[0])}
            )
            if row is not None
            else None
        )

    def list_option_chains(
        self,
        symbol: str,
        through_timestamp: datetime,
    ) -> list[OptionsContext]:
        self.initialize()
        cutoff = aware_utc(through_timestamp).isoformat()
        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, payload_json
                FROM option_chain_snapshots
                WHERE symbol = ? AND data_as_of <= ?
                  AND retrieved_at IS NOT NULL AND retrieved_at <= ?
                  AND created_at <= ?
                ORDER BY data_as_of, id
                """,
                (symbol.upper(), cutoff, cutoff, cutoff),
            ).fetchall()
        return [
            OptionsContext.model_validate_json(row[1]).model_copy(
                update={"snapshot_id": int(row[0])}
            )
            for row in rows
        ]

    def list_accounts(self, through_timestamp: datetime) -> list[AccountRiskContext]:
        self.initialize()
        cutoff = aware_utc(through_timestamp).isoformat()
        with connect_sqlite(self.database_path) as connection:
            account_ids = connection.execute(
                """
                SELECT DISTINCT account_id
                FROM account_snapshots
                WHERE data_as_of <= ? AND retrieved_at IS NOT NULL
                  AND retrieved_at <= ? AND created_at <= ?
                """,
                (cutoff, cutoff, cutoff),
            ).fetchall()
            if len(account_ids) != 1:
                return []
            rows = connection.execute(
                """
                SELECT id, payload_json
                FROM account_snapshots
                WHERE account_id = ? AND data_as_of <= ?
                  AND retrieved_at IS NOT NULL AND retrieved_at <= ?
                  AND created_at <= ?
                ORDER BY data_as_of, id
                """,
                (account_ids[0][0], cutoff, cutoff, cutoff),
            ).fetchall()
        return [
            AccountRiskContext.model_validate_json(row[1]).model_copy(
                update={"snapshot_id": int(row[0])}
            )
            for row in rows
        ]


def _ensure_column(connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
