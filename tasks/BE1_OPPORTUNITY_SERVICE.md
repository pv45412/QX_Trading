# Task Contract: BE1 Canonical Opportunity Service / Persistence Contract

- **task_id:** BE1
- **title:** Canonical Opportunity Service / Persistence Contract
- **current state:** COMPLETE

## Goal

Define and implement one backend-owned, read-only opportunity contract for Today and Opportunities, preserving canonical `core_v1` evaluations, identities, provenance, and point-in-time semantics.

## Dependencies

- UX6 is COMPLETE.
- Current canonical pipeline and shadow telemetry remain verified.

## In scope

- Opportunity DTO/query contract, stable evaluation identity, lifecycle state, reasons, evidence coverage, freshness, and provenance.
- Read-only aggregation of canonical evaluations without frontend rescoring.
- Persistence contract design for opportunity observations where required.
- Pagination/filtering and bounded query behavior.

## Out of scope

- Multi-timeframe semantics, Market Driver logic, Journal records, execution, broker writes, and rule/threshold changes.
- Replacement or deletion of legacy scanners.

## Acceptance criteria

- Today and Opportunities can consume one canonical service contract.
- Stored/retrieved observations preserve `pipeline_version="core_v1"`, evaluation timestamp, identity, and point-in-time visibility.
- Missing data remains unavailable; no synthetic opportunity or lifecycle promotion occurs.
- Repeated reads do not trigger duplicate pipeline evaluation unless explicitly requested.
- Any new persistence/domain model receives human approval before implementation.

## Required tests

- Unit tests for identity, serialization, filtering, deduplication, and null preservation.
- Point-in-time and future-data exclusion tests.
- API/integration tests for Today and Opportunities consumers.
- Pipeline regression, full maintained unit suite, and preflight.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- QA Gatekeeper
- Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

Implementation repair cycle 3 ended with an unresolved Architecture Checker blocker: migration checksum/schema drift is detected by the migration layer but suppressed during application construction, allowing the opportunity router to remain available. One additional repair cycle is explicitly human-authorized and strictly limited to fail-closed opportunity-store initialization plus regression coverage.

The additional human-authorized repair cycle ended with a Data/Security Checker blocker: migration-ledger DDL drift with unchanged columns and checksums was not detected.

Human Decision Option A was authorized and implemented: Canonical DDL fingerprinting and actual schema inspection from `sqlite_master` were added. All 7 adversarial test cases pass. Architecture, Data/Security, and QA checkers returned PASS. Human review accepted the design, and the full maintained unit suite passed 100% green (2,331 passed). BE1 is COMPLETE.

## Human gate conditions

New persistent domain models, trading semantics, thresholds/weights, scanner replacement, destructive migration, vendor changes, or security architecture require explicit human approval.

## Rollback / compatibility requirements

Additive versioned API/persistence changes only. Existing canonical v2 and legacy discovery paths remain available until separately migrated and approved.

## Final deliverables

- Approved service and persistence contract
- API/schema documentation and dependency map
- Consumer migration plan
- Test/performance evidence
- Checker verdicts and rollback procedure

## UI preview requirement

If visible UI changes enter approved scope, follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.

## Architecture review evidence

- Design package: `data/reports/be1_architecture/`
- The initial architecture review exhausted its repair allowance and correctly entered `HUMAN_REQUIRED`.
- Human approval resolved latest-per-stream ordering, command reconciliation, ETag semantics, migration-zero behavior, and authoritative database configuration.
- Production implementation is authorized only within this contract and the approved architecture package.
- Implementation receives a fresh maximum of three automatic repair cycles.
- Required human decisions are recorded in `data/reports/be1_architecture/BE1_ARCHITECTURE_PROPOSAL.md`.

## Authoritative architecture decisions

1. Apply hard eligibility and point-in-time boundaries before latest-per-stream selection; apply presentation filters only after deterministic latest selection.
2. Publication commands use `RESERVED`, `COMMITTED`, and `ABANDONED`; reconciliation never creates opportunity records.
3. Strong ETags hash exact deterministic response bytes before compression; otherwise use weak ETags.
4. Migration 000 uses strict `CREATE TABLE`; ledger/checksum state provides idempotency and schema drift fails closed.
5. Opportunity persistence reuses the typed canonical runtime SQLite database configuration and never creates a separate database.
