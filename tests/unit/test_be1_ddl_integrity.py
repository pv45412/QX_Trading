from __future__ import annotations

import sqlite3
import pytest
from fastapi.testclient import TestClient

from qx.interfaces.web import create_app
from qx.opportunities.migrations import (
    CANONICAL_DDL_FINGERPRINTS,
    CANONICAL_SCHEMA_FINGERPRINT,
    CANONICAL_SCHEMA_STATEMENTS,
    MIGRATION_000,
    MIGRATION_000_SQL,
    MIGRATION_001,
    MIGRATION_001_STATEMENTS,
    OpportunityMigrationError,
    apply_opportunity_migrations,
    compute_ddl_fingerprint,
    compute_schema_fingerprint,
    normalize_ddl,
    read_actual_schema_ddl,
    validate_schema_fingerprints,
)
from qx.opportunities.repository import OpportunityRepository


def test_identical_expected_ddl_passes(tmp_path) -> None:
    """1. Identical expected DDL passes fingerprint validation and initialization."""
    database = tmp_path / "clean.db"
    apply_opportunity_migrations(str(database))

    with sqlite3.connect(database) as conn:
        actual = read_actual_schema_ddl(conn)
        validate_schema_fingerprints(conn)
        assert compute_schema_fingerprint(actual) == CANONICAL_SCHEMA_FINGERPRINT

    # Mount in app: must return 200 with empty items, never 503
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    client = TestClient(app)
    response = client.get(
        "/api/v2/qx/opportunities",
        params={"query_as_of": "2026-09-16T14:30:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_whitespace_only_ddl_difference_passes(tmp_path) -> None:
    """2. Whitespace-only DDL differences pass if normalization defines equivalence."""
    database = tmp_path / "whitespace.db"

    # Create tables with varied whitespace, newlines, tabs, and comments
    whitespace_migration_000 = """
        -- Leading comment
        CREATE   TABLE   qx_schema_migrations   (
            migration_id   TEXT   PRIMARY   KEY  ,
            migration_checksum   TEXT   NOT   NULL  ,
            applied_at   TEXT   NOT   NULL  ,
            application_version   TEXT   NOT   NULL
        )  ;
    """

    assert normalize_ddl(whitespace_migration_000) == normalize_ddl(MIGRATION_000_SQL)
    assert compute_ddl_fingerprint(whitespace_migration_000) == CANONICAL_DDL_FINGERPRINTS["qx_schema_migrations"]

    with sqlite3.connect(database) as conn:
        conn.execute(whitespace_migration_000)
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    # apply_opportunity_migrations should accept the whitespace-equivalent ledger table and proceed
    apply_opportunity_migrations(str(database))

    with sqlite3.connect(database) as conn:
        validate_schema_fingerprints(conn)


def test_reordered_or_altered_constraints_block(tmp_path) -> None:
    """3. Reordered or semantically altered constraints block initialization."""
    database = tmp_path / "reordered.db"

    # Reorder NOT NULL and CHECK constraint on status column
    reordered_commands_sql = """CREATE TABLE opportunity_publication_commands (
        idempotency_key TEXT PRIMARY KEY,
        payload_hash TEXT NOT NULL,
        producer_id TEXT NOT NULL,
        producer_run_id TEXT NOT NULL,
        status TEXT CHECK (status IN ('RESERVED', 'COMMITTED', 'ABANDONED')) NOT NULL,
        evaluation_id TEXT,
        attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
        reserved_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        committed_at TEXT,
        abandoned_at TEXT,
        failure_code TEXT
    )"""

    assert normalize_ddl(reordered_commands_sql) != normalize_ddl(MIGRATION_001_STATEMENTS[0])
    assert compute_ddl_fingerprint(reordered_commands_sql) != CANONICAL_DDL_FINGERPRINTS["opportunity_publication_commands"]

    with sqlite3.connect(database) as conn:
        conn.execute(MIGRATION_000_SQL)
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.execute(reordered_commands_sql)
        conn.execute(MIGRATION_001_STATEMENTS[1])
        conn.execute(MIGRATION_001_STATEMENTS[2])
        conn.execute(MIGRATION_001_STATEMENTS[3])
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_001.migration_id, MIGRATION_001.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    with pytest.raises(OpportunityMigrationError, match="drift detected for opportunity_publication_commands"):
        apply_opportunity_migrations(str(database))

    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    client = TestClient(app)
    response = client.get("/api/v2/qx/opportunities")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPPORTUNITY_STORE_SCHEMA_INVALID"


def test_changed_constraints_and_nullability_block(tmp_path) -> None:
    """4. Changed default, nullability, unique, primary key, or check constraints block."""
    # Subtest A: Missing NOT NULL in ledger
    db_notnull = tmp_path / "notnull.db"
    with sqlite3.connect(db_notnull) as conn:
        conn.execute("""CREATE TABLE qx_schema_migrations (
            migration_id TEXT PRIMARY KEY,
            migration_checksum TEXT,
            applied_at TEXT NOT NULL,
            application_version TEXT NOT NULL
        )""")
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    with pytest.raises(OpportunityMigrationError):
        apply_opportunity_migrations(str(db_notnull))

    # Subtest B: Altered CHECK constraint condition (attempt_count >= 0 instead of >= 1)
    db_check = tmp_path / "check.db"
    with sqlite3.connect(db_check) as conn:
        conn.execute(MIGRATION_000_SQL)
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        altered_commands = MIGRATION_001_STATEMENTS[0].replace("attempt_count >= 1", "attempt_count >= 0")
        conn.execute(altered_commands)
        conn.execute(MIGRATION_001_STATEMENTS[1])
        conn.execute(MIGRATION_001_STATEMENTS[2])
        conn.execute(MIGRATION_001_STATEMENTS[3])
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_001.migration_id, MIGRATION_001.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    with pytest.raises(OpportunityMigrationError, match="drift detected"):
        apply_opportunity_migrations(str(db_check))

    # Subtest C: Missing UNIQUE on idempotency_key in evaluations
    db_unique = tmp_path / "unique.db"
    with sqlite3.connect(db_unique) as conn:
        conn.execute(MIGRATION_000_SQL)
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.execute(MIGRATION_001_STATEMENTS[0])
        altered_evaluations = MIGRATION_001_STATEMENTS[1].replace("idempotency_key TEXT NOT NULL UNIQUE,", "idempotency_key TEXT NOT NULL,")
        conn.execute(altered_evaluations)
        conn.execute(MIGRATION_001_STATEMENTS[2])
        conn.execute(MIGRATION_001_STATEMENTS[3])
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_001.migration_id, MIGRATION_001.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    with pytest.raises(OpportunityMigrationError, match="drift detected for opportunity_evaluations"):
        apply_opportunity_migrations(str(db_unique))


def test_altered_create_table_text_with_same_columns_blocks(tmp_path) -> None:
    """5. Altered CREATE TABLE text with same columns (e.g. extra CHECK 1=1) blocks."""
    database = tmp_path / "same_columns_extra_check.db"
    with sqlite3.connect(database) as conn:
        conn.execute("""CREATE TABLE qx_schema_migrations (
            migration_id TEXT PRIMARY KEY,
            migration_checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            application_version TEXT NOT NULL,
            CHECK (1=1)
        )""")
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    with pytest.raises(OpportunityMigrationError, match="Migration ledger DDL fingerprint mismatch"):
        apply_opportunity_migrations(str(database))

    # Test via create_app: fails closed, never serves LIVE 200
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    client = TestClient(app)
    response = client.get("/api/v2/qx/opportunities")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPPORTUNITY_STORE_SCHEMA_INVALID"


def test_checksum_match_but_ddl_drift_blocks(tmp_path) -> None:
    """6. When migration ledger has matching checksums but DDL has drifted, block and return 503."""
    database = tmp_path / "checksum_match_ddl_drift.db"
    with sqlite3.connect(database) as conn:
        conn.execute(MIGRATION_000_SQL)
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_000.migration_id, MIGRATION_000.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        # Create opportunity_publication_commands with an altered column type
        drifted_commands = MIGRATION_001_STATEMENTS[0].replace(
            "attempt_count INTEGER NOT NULL", "attempt_count BIGINT NOT NULL"
        )
        conn.execute(drifted_commands)
        conn.execute(MIGRATION_001_STATEMENTS[1])
        conn.execute(MIGRATION_001_STATEMENTS[2])
        conn.execute(MIGRATION_001_STATEMENTS[3])
        # Record canonical checksum in ledger
        conn.execute(
            "INSERT INTO qx_schema_migrations VALUES (?, ?, ?, ?)",
            (MIGRATION_001.migration_id, MIGRATION_001.checksum, "2026-09-16T00:00:00Z", "be1"),
        )
        conn.commit()

    with pytest.raises(OpportunityMigrationError, match="drift detected for opportunity_publication_commands"):
        apply_opportunity_migrations(str(database))

    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    client = TestClient(app)
    response = client.get("/api/v2/qx/opportunities")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPPORTUNITY_STORE_SCHEMA_INVALID"


def test_valid_restored_schema_passes(tmp_path) -> None:
    """7. Restoring the valid schema resolves drift and returns HTTP 200."""
    database = tmp_path / "restore.db"

    # First, create drifted schema
    conn = sqlite3.connect(database)
    try:
        conn.execute("""CREATE TABLE qx_schema_migrations (
            migration_id TEXT PRIMARY KEY,
            migration_checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            application_version TEXT NOT NULL,
            CHECK (1=1)
        )""")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(OpportunityMigrationError):
        apply_opportunity_migrations(str(database))

    # Now simulate a restore by recreating with canonical DDL
    database.unlink()
    apply_opportunity_migrations(str(database))

    # Re-test app mounting: returns 200 OK
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    client = TestClient(app)
    response = client.get(
        "/api/v2/qx/opportunities",
        params={"query_as_of": "2026-09-16T14:30:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
