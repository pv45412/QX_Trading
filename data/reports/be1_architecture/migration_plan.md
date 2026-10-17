# BE1 Migration Plan

## Preconditions

- Human approval of the OpportunityRecord domain and schema.
- Human approval of the typed canonical runtime database path, identity/idempotency model, internal LIVE publisher boundary, and non-destructive retention policy has been received.
- BE1 never invents timeframe TTLs. An approved internal producer must supply `expires_at` and `freshness_policy_version`; absent values fail closed.
- No Phase 3-10, threshold, playbook, Market Driver, execution, or vendor changes.

## Phase 0 — Contract Lock

Freeze DTOs, identity rules, privacy allowlist, state behavior, mode boundaries, and failure semantics. Use contract fixtures only; no production writes.

## Phase 1 — Additive Storage Disabled

Bootstrap and validate the fixed migration-zero ledger first using strict `CREATE TABLE`. Then add the checksummed BE1 migration, publication-command reservation table, and repository. Apply BE1 target DDL and ledger row in one separate `BEGIN IMMEDIATE` transaction. Any checksum mismatch, pre-existing unledgered object, ledger-schema mismatch, or partial-state evidence fails closed for human reconciliation.

## Phase 2 — Internal Dual-Write Validation

An approved producer calls `run_pipeline()` once and passes its result to the publisher. Compare persisted/reloaded projections field-for-field. Reads remain internal and UI remains unchanged.

## Phase 3 — Read-Only API

Expose bounded list/detail endpoints behind a feature flag. Validate point-in-time visibility, mode isolation, pagination, concurrency, and performance.

## Phase 4 — Today Migration

Move only Active Opportunities to list reads. Preserve Today attention hierarchy, market-pulse ownership, and unavailable states. Follow `tasks/UI_PREVIEW_LOOP.md`.

## Phase 5 — Opportunities Migration

Replace fixture-only canonical availability with server records while keeping legacy discovery separate. Preserve filters and canonical/legacy labeling. Follow the UI preview loop.

## Phase 6 — Trade Exact Identity

Use detail-by-ID for canonical handoffs. Missing records fail visibly. Explicit direct evaluation remains a clearly labeled ephemeral RESEARCH result and does not create a LIVE opportunity identity. Follow the UI preview loop.

## Phase 7 — Observation and Acceptance

Run sustained read/write observation, measure database growth/query latency, execute checker gates, and request human acceptance. Do not delete legacy routes.

## No Backfill

- Do not convert shadow telemetry into LIVE records.
- Do not convert replay observations into LIVE records.
- Do not infer identities from partial legacy rows.
- Any future historical import retains a non-LIVE mode in isolated storage.

## Rollback

1. Disable publisher writes.
2. Disable list/detail route registration or feature flag.
3. Restore Today, Opportunities, and Trade to their prior paths.
4. Preserve new tables for audit; do not drop automatically.
5. Verify v2 evaluation, shadow, replay, snapshots, and legacy discovery remain unchanged.

Dropping tables or purging records is a separate destructive human gate.
