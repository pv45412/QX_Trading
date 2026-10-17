# Task Contract: JR1 Journal / Outcome Persistence

- **task_id:** JR1
- **title:** Journal / Outcome Persistence
- **current state:** BACKLOG

## Goal

Create an approved durable domain and persistence model for ideas, canonical evaluations, trades when they exist, and measured outcomes without relabeling legacy position tools as a Journal.

## Dependencies

- BE1 is COMPLETE and exposes stable canonical opportunity/evaluation identity.
- Journal persistence/domain design receives explicit human approval.

## In scope

- Domain model and schema for ideas, evaluation links, annotations, status history, and outcomes.
- Privacy-safe identifiers, migrations, read/write API boundaries, audit timestamps, retention, and export/rollback strategy.
- Journal remains secondary in navigation.

## Out of scope

- Broker orders, execution claims, fabricated fills/outcomes, rule optimization, analytics promoted into live confidence, and destructive legacy removal.

## Acceptance criteria

- Human-approved domain model clearly separates signal, trade, and outcome concepts.
- `signal_r` is never presented as actual trade return; realized outcomes require real persisted events.
- Writes are idempotent, auditable, privacy-safe, and transactionally tested.
- Missing trade/fill data remains unavailable rather than inferred.
- Legacy routes remain compatible until separate migration approval.

## Required tests

- Schema/migration, idempotency, transaction, concurrency, rollback, privacy, and redaction tests.
- API authorization and validation tests.
- Canonical identity linkage and historical-data integrity tests.
- Full maintained unit suite, regression, and preflight.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- Security/Data Governance Checker
- QA Gatekeeper
- UI Checker where Journal UI is included

## Automatic repair allowance

Maximum 3 automatic repair cycles after domain-model approval. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

The persistence/domain model, destructive migrations, retention policy, security/auth changes, and any execution linkage require explicit human approval.

## Rollback / compatibility requirements

Use reversible migrations and additive APIs. Back up persisted records before migration and preserve legacy read paths until validated migration approval.

## Final deliverables

- Approved domain/schema specification
- Migrations and persistence/API implementation
- Privacy and rollback documentation
- Test/checker evidence
- Journal UI evidence if separately included in approved scope

## UI preview requirement

Any separately approved Journal UI work must follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.
