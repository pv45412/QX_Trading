from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from qx.storage.connection import connect_sqlite


class OpportunityMigrationError(RuntimeError):
    pass


MIGRATION_000_SQL = """CREATE TABLE qx_schema_migrations (
    migration_id TEXT PRIMARY KEY,
    migration_checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    application_version TEXT NOT NULL
)"""

MIGRATION_001_STATEMENTS = (
    """CREATE TABLE opportunity_publication_commands (
        idempotency_key TEXT PRIMARY KEY,
        payload_hash TEXT NOT NULL,
        producer_id TEXT NOT NULL,
        producer_run_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('RESERVED', 'COMMITTED', 'ABANDONED')),
        evaluation_id TEXT,
        attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
        reserved_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        committed_at TEXT,
        abandoned_at TEXT,
        failure_code TEXT
    )""",
    """CREATE TABLE opportunity_evaluations (
        evaluation_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        schema_version TEXT NOT NULL,
        observation_mode TEXT NOT NULL CHECK (observation_mode = 'LIVE'),
        environment_id TEXT NOT NULL,
        producer_id TEXT NOT NULL,
        producer_run_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        horizon_context TEXT,
        evaluation_timestamp TEXT NOT NULL,
        request_started_at TEXT,
        recorded_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        freshness_policy_version TEXT NOT NULL,
        publication_state TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL,
        pipeline_version TEXT NOT NULL,
        config_version TEXT NOT NULL,
        engine_versions_json TEXT NOT NULL,
        direction TEXT,
        primary_playbook_id TEXT,
        source_setup_reference TEXT,
        reason_codes_json TEXT NOT NULL,
        evidence_coverage REAL,
        coverage_status TEXT,
        data_dependencies_json TEXT NOT NULL,
        decision_payload_json TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL,
        bar_window_sha256 TEXT NOT NULL,
        result_sha256 TEXT NOT NULL,
        stream_key TEXT NOT NULL,
        supersedes_evaluation_id TEXT,
        FOREIGN KEY(idempotency_key) REFERENCES opportunity_publication_commands(idempotency_key)
    )""",
    """CREATE INDEX idx_opportunity_current_query
       ON opportunity_evaluations(
           observation_mode, environment_id, publication_state,
           evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
       )""",
    """CREATE INDEX idx_opportunity_stream_query
       ON opportunity_evaluations(
           stream_key, evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
       )""",
)


CANONICAL_SCHEMA_STATEMENTS: dict[str, str] = {
    "qx_schema_migrations": MIGRATION_000_SQL,
    "opportunity_publication_commands": MIGRATION_001_STATEMENTS[0],
    "opportunity_evaluations": MIGRATION_001_STATEMENTS[1],
    "idx_opportunity_current_query": MIGRATION_001_STATEMENTS[2],
    "idx_opportunity_stream_query": MIGRATION_001_STATEMENTS[3],
}


def normalize_ddl(sql: str) -> str:
    """Normalize DDL deterministically for schema fingerprinting.

    Equivalence rules:
    - Strips single-line SQL comments (-- ...).
    - Strips leading/trailing whitespace, newlines, and trailing semicolons.
    - Collapses all consecutive whitespace sequences to a single ASCII space.
    - Standardizes spacing around commas (comma followed by single space, no leading space).
    - Standardizes spacing around parentheses (no inner padding spaces, no space before open paren).
    """
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = sql.strip().rstrip(";").strip()
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"\s*,\s*", ", ", sql)
    sql = re.sub(r"\s*\(\s*", "(", sql)
    sql = re.sub(r"\s*\)\s*", ")", sql)
    return sql


def _normalize_sql(value: str) -> str:
    return normalize_ddl(value)


def compute_ddl_fingerprint(sql: str) -> str:
    """Compute deterministic SHA-256 fingerprint for a single normalized DDL statement."""
    normalized = normalize_ddl(sql)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_schema_fingerprint(statements: dict[str, str]) -> str:
    """Compute deterministic composite SHA-256 fingerprint over all schema objects."""
    parts = []
    for name in sorted(statements.keys()):
        norm = normalize_ddl(statements[name])
        parts.append(f"{name}:{norm}")
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


CANONICAL_SCHEMA_FINGERPRINT = compute_schema_fingerprint(CANONICAL_SCHEMA_STATEMENTS)
CANONICAL_DDL_FINGERPRINTS: dict[str, str] = {
    name: compute_ddl_fingerprint(sql)
    for name, sql in CANONICAL_SCHEMA_STATEMENTS.items()
}


@dataclass(frozen=True)
class Migration:
    migration_id: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        normalized = "\n-- statement --\n".join(statement.strip() for statement in self.statements)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


MIGRATION_000 = Migration("000_qx_schema_migrations", (MIGRATION_000_SQL,))
MIGRATION_001 = Migration("001_be1_opportunity_v1", MIGRATION_001_STATEMENTS)

LEDGER_COLUMNS = (
    ("migration_id", "TEXT", 0, 1),
    ("migration_checksum", "TEXT", 1, 0),
    ("applied_at", "TEXT", 1, 0),
    ("application_version", "TEXT", 1, 0),
)


def read_actual_schema_ddl(connection: sqlite3.Connection) -> dict[str, str]:
    """Read actual DDL for BE1-managed tables and indexes from sqlite_master."""
    rows = connection.execute(
        """SELECT name, sql FROM sqlite_master
           WHERE name IN (?, ?, ?, ?, ?)""",
        tuple(CANONICAL_SCHEMA_STATEMENTS),
    ).fetchall()
    return {row[0]: row[1] for row in rows if row[1] is not None}


def validate_schema_fingerprints(connection: sqlite3.Connection) -> None:
    """Verify all actual schema objects match approved canonical DDL fingerprints."""
    actual = read_actual_schema_ddl(connection)
    if set(actual) != set(CANONICAL_SCHEMA_STATEMENTS):
        raise OpportunityMigrationError("BE1 schema objects are incomplete")
    for name, expected_fp in CANONICAL_DDL_FINGERPRINTS.items():
        actual_sql = actual.get(name)
        if not actual_sql:
            raise OpportunityMigrationError(f"BE1 schema object missing DDL for {name}")
        actual_fp = compute_ddl_fingerprint(actual_sql)
        if actual_fp != expected_fp:
            raise OpportunityMigrationError(
                f"BE1 schema DDL fingerprint mismatch for {name}: expected {expected_fp}, got {actual_fp}"
            )
    actual_composite = compute_schema_fingerprint(actual)
    if actual_composite != CANONICAL_SCHEMA_FINGERPRINT:
        raise OpportunityMigrationError("BE1 composite schema fingerprint mismatch")


def apply_opportunity_migrations(database_path: str) -> None:
    try:
        connection = connect_sqlite(database_path)
    except sqlite3.Error as exc:
        raise OpportunityMigrationError("Opportunity database connection failed") from exc
    try:
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            _apply_migration_zero(connection)
            _apply_migration(connection, MIGRATION_001)
            validate_schema_fingerprints(connection)
        except sqlite3.Error as exc:
            raise OpportunityMigrationError("Opportunity migration inspection failed") from exc
    finally:
        connection.close()


def _apply_migration_zero(connection: sqlite3.Connection) -> None:
    exists = _object_exists(connection, "table", "qx_schema_migrations")
    if not exists:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(MIGRATION_000_SQL)
            connection.execute(
                "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
                (
                    MIGRATION_000.migration_id,
                    MIGRATION_000.checksum,
                    _now(),
                    "be1",
                ),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise OpportunityMigrationError("Migration 000 failed") from exc
    _validate_ledger_schema(connection)
    row = connection.execute(
        "SELECT migration_checksum FROM qx_schema_migrations WHERE migration_id = ?",
        (MIGRATION_000.migration_id,),
    ).fetchone()
    if row is None:
        raise OpportunityMigrationError("Migration ledger does not prove migration 000")
    if row[0] != MIGRATION_000.checksum:
        raise OpportunityMigrationError("Migration 000 checksum mismatch")


def _apply_migration(connection: sqlite3.Connection, migration: Migration) -> None:
    row = connection.execute(
        "SELECT migration_checksum FROM qx_schema_migrations WHERE migration_id = ?",
        (migration.migration_id,),
    ).fetchone()
    if row is not None:
        if row[0] != migration.checksum:
            raise OpportunityMigrationError(f"{migration.migration_id} checksum mismatch")
        _validate_target_schema(connection)
        return
    target_names = (
        "opportunity_publication_commands",
        "opportunity_evaluations",
        "idx_opportunity_current_query",
        "idx_opportunity_stream_query",
    )
    if any(_named_object_exists(connection, name) for name in target_names):
        raise OpportunityMigrationError("Unledgered BE1 schema objects detected")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (migration.migration_id, migration.checksum, _now(), "be1"),
        )
        _validate_target_schema(connection)
        connection.commit()
    except (sqlite3.Error, OpportunityMigrationError) as exc:
        connection.rollback()
        if isinstance(exc, OpportunityMigrationError):
            raise
        raise OpportunityMigrationError(f"{migration.migration_id} failed") from exc


def _validate_ledger_schema(connection: sqlite3.Connection) -> None:
    columns = tuple(
        (row[1], row[2].upper(), row[3], row[5])
        for row in connection.execute("PRAGMA table_info(qx_schema_migrations)")
    )
    if columns != LEDGER_COLUMNS:
        raise OpportunityMigrationError("Migration ledger schema mismatch")
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'qx_schema_migrations'"
    ).fetchone()
    if not row or not row[0]:
        raise OpportunityMigrationError("Migration ledger DDL missing")
    actual_fp = compute_ddl_fingerprint(row[0])
    expected_fp = CANONICAL_DDL_FINGERPRINTS["qx_schema_migrations"]
    if actual_fp != expected_fp:
        raise OpportunityMigrationError("Migration ledger DDL fingerprint mismatch")


def _validate_target_schema(connection: sqlite3.Connection) -> None:
    target_names = (
        "opportunity_publication_commands",
        "opportunity_evaluations",
        "idx_opportunity_current_query",
        "idx_opportunity_stream_query",
    )
    rows = connection.execute(
        """SELECT name, sql FROM sqlite_master
           WHERE name IN (?, ?, ?, ?)""",
        target_names,
    ).fetchall()
    actual = {row[0]: row[1] for row in rows if row[1] is not None}
    if set(actual) != set(target_names):
        raise OpportunityMigrationError("BE1 schema objects are incomplete")
    for name in target_names:
        actual_sql = actual[name]
        actual_fp = compute_ddl_fingerprint(actual_sql)
        expected_fp = CANONICAL_DDL_FINGERPRINTS[name]
        if actual_fp != expected_fp:
            raise OpportunityMigrationError(f"BE1 schema drift detected for {name}")


def _object_exists(connection: sqlite3.Connection, object_type: str, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?", (object_type, name)
        ).fetchone()
        is not None
    )


def _named_object_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone()
        is not None
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
