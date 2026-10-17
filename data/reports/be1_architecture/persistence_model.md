# BE1 Persistence Model

## Choice

Use additive SQLite persistence through the existing WAL connection factory. The typed `Settings.runtime_database_path` setting is authoritative and defaults to `data/scanner_history.db`. BE1 does not create an opportunity-specific database or introduce a database vendor, queue, Redis, or distributed store.

## Proposed Schema

Migration-zero bootstrap, applied separately and validated before BE1 migration lookup:

```sql
CREATE TABLE qx_schema_migrations (
    migration_id TEXT PRIMARY KEY,
    migration_checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    application_version TEXT NOT NULL
);
```

BE1 target migration SQL:

```sql

CREATE TABLE opportunity_publication_commands (
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
);

CREATE TABLE opportunity_evaluations (
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
);

CREATE INDEX idx_opportunity_current_query
ON opportunity_evaluations(
    observation_mode, environment_id, publication_state,
    evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
);

CREATE INDEX idx_opportunity_stream_query
ON opportunity_evaluations(
    stream_key, evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
);
```

The DDL is human-approved and implemented in `src/qx/opportunities/migrations.py`. JSON uses canonical sorted compact encoding and strict model validation on write/read.

`idempotency_key` is globally namespaced by hashing environment ID, producer ID, producer run ID, symbol, timeframe, and command schema version. Live evaluation time is excluded because it is established after provider acquisition; it is included in `input_fingerprint`. The database primary key therefore includes the command namespace cryptographically rather than relying on an unscoped human string.

## Migration Ledger Procedure

The implemented migration IDs are `000_qx_schema_migrations` and `001_be1_opportunity_v1`. Their SHA-256 checksums are computed from the exact normalized SQL committed with the implementation.

1. Open the authoritative database and execute a migration-zero `BEGIN IMMEDIATE`.
2. If the ledger is absent, run only the fixed, checksummed strict `CREATE TABLE qx_schema_migrations (...)` statement and insert migration 000 in the same transaction.
3. Validate the ledger's exact columns, types, primary key, and absence of unexpected columns with `PRAGMA table_info`; mismatch rolls back and fails startup.
4. Commit migration zero.
5. Start a new `BEGIN IMMEDIATE` for `be1_opportunity_v1` and query the ledger.
6. If the migration ID exists with the same checksum, commit as an idempotent no-op without replaying target DDL.
7. If the ID exists with a different checksum, roll back and fail startup.
8. If BE1 target objects exist without a matching ledger entry, roll back and require human reconciliation.
9. Apply BE1 target DDL exactly once and insert its ledger row in the same transaction.
10. Run schema/constraint/index verification before commit.

Migration-zero SQL is fixed and separately checksummed. SQLite transactional DDL ensures interruption rolls back each transaction. No startup path may silently repair a partial, mismatched, or unledgered target migration.

## Transaction and Idempotency

Command reservation occurs in a bounded transaction before acquisition/evaluation:

1. Validate internal LIVE publisher capability.
2. Insert a RESERVED idempotency key before any provider or pipeline call.
3. Existing COMMITTED key returns its evaluation ID without rerunning.
4. A RESERVED key inside the reconciliation TTL returns an in-progress conflict.
5. A RESERVED key past the TTL with no immutable record becomes ABANDONED; reconciliation never creates a record.
6. An ABANDONED key with the same payload hash may be atomically re-reserved and increments attempt metadata; a different payload hash conflicts.

After one pipeline invocation, a second transaction validates privacy, identity, digest, provenance, and point-in-time invariants, inserts the immutable record, and marks the command COMMITTED. The insert and state transition are atomic. A crash before that transaction commits leaves only a RESERVED command, which becomes eligible for ABANDONED reconciliation after the configured operational TTL.

No update path exists for canonical payload columns. Explicit corrections create new records with a supersession reference.

The input fingerprint includes `bar_window_sha256`, timeframe, ordered first/last bar timestamps, bar count, source provenance, and safe option/account snapshot visibility references.

## Stored Versus Referenced

Store safe decision fields and provenance. Reference option/account snapshot IDs. Do not duplicate bars, option chains, account snapshots, account balances, positions, or provider payloads. Because shared connections do not currently enable foreign-key enforcement, referenced snapshots require explicit repository validation or a separately approved connection change.

## Point-in-Time Visibility

Historical list/detail authorization requires:

```text
evaluation_timestamp <= requested_market_time
recorded_at <= requested_knowledge_time
```

Dependency provenance must also show source data and retrieval visibility no later than evaluation time. Missing provenance fails closed.

For bars, LIVE publication additionally requires a validated cache sidecar content hash and retrieval timestamp. Filesystem modification time is not accepted as provider retrieval time.

## Retention and Archive

Initial recommendation: no destructive deletion. Measure growth first.

A later human-approved archive may export old immutable records to checksummed compressed files, verify counts/hashes, retain referenced records online, and purge only after destructive-migration approval. No policy may delete records still referenced by another domain.

## Concurrency and Performance

- Retain SQLite WAL and bounded busy timeout.
- Keep writes short and deterministic.
- Use indexed cursor queries with strict limits.
- Database busy/unavailable returns an explicit error; it does not trigger reevaluation or drop data silently.
- Add a materialized current-head table only if PERF evidence later justifies it.
