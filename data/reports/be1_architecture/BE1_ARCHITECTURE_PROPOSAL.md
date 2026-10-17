# BE1 Architecture Proposal

## Status

- Milestone: BE1 Canonical Opportunity Service / Persistence Contract
- Review type: design and architecture only
- Production implementation: not authorized
- New persistent domain model: requires explicit human approval
- UI preview policy: NOT_APPLICABLE; no visible UI is changed
- Governance state: IN_PROGRESS after human architecture approval

## Human-Approved Architecture Decisions

The prior checker blockers were resolved by explicit human approval:

1. Hard source, publication, environment, point-in-time, and current-only expiry boundaries apply before stream partitioning. The latest eligible record is selected per stream before lifecycle, direction, playbook, horizon, and other presentation filters.
2. Commands use `RESERVED`, `COMMITTED`, and `ABANDONED`. Expired reservations without a committed record may be reconciled to `ABANDONED`; reconciliation never manufactures a record. Identical retries may atomically re-reserve an abandoned command, while payload-hash mismatches conflict.
3. Strong ETags hash the exact deterministic served response bytes before compression. Implementations unable to guarantee byte equivalence must use weak ETags.
4. Migration 000 uses strict `CREATE TABLE`, never `IF NOT EXISTS`. Recorded matching migrations skip safely; checksum mismatch or an unproven pre-existing table fails closed.
5. BE1 reuses the typed canonical runtime SQLite database setting, historically defaulting to `data/scanner_history.db`; it must not create an opportunity-specific database.

## Executive Decision

BE1 should persist an immutable, backend-owned projection of individual `run_pipeline()` results. One `OpportunityRecord` represents exactly one canonical evaluation. It is not a setup lifecycle and not a symbol/timeframe stream. Ordered records form an evaluation timeline; an indexed query identifies the newest visible record without rewriting history.

The service must never rescore, infer, promote, or merge lifecycle states. It copies canonical output fields verbatim, adds storage metadata, and exposes read-only queries. Trade retrieves an exact stored evaluation by `evaluation_id`. Today and Opportunities query stored records without calling `run_pipeline()` as a read side effect.

## Preimplementation Repository Facts

- `qx.pipeline.orchestrator.run_pipeline()` is the only canonical Phase 3-10 decision chain.
- `QXEvaluationResult` has no backend-owned `evaluation_id`, observation mode, or input fingerprint.
- Today directly evaluates SPY and QQQ and has no canonical opportunity-list service.
- Opportunities previously had fixture canonical rows or an explicit unavailable state; legacy movers remain separate discovery context.
- Trade previously accepted an evaluation ID in URL context but reran by timestamp because no stored-record endpoint existed.
- Shadow and replay observations already use separate persistence paths and must remain isolated from live opportunities.
- The prior application database defaults were ambiguous; BE1 resolves runtime persistence through `Settings.runtime_database_path`, defaulting to `data/scanner_history.db`, while retaining the legacy `database_url` compatibility field.

## Proposed Components

1. `OpportunityRecord`: immutable versioned projection copied from one canonical evaluation.
2. `OpportunityIdentity`: opaque evaluation ID, producer idempotency key, input fingerprint, and result digest.
3. `OpportunityRepository`: additive SQLite WAL persistence for approved LIVE publisher records.
4. `PublicationCommandRepository`: reserves producer idempotency before provider or pipeline work.
5. `OpportunityPublisher`: post-pipeline adapter that records a completed result and never invokes phase engines.
6. `OpportunityQueryService`: bounded read-only list/detail queries with hard LIVE scope.
7. Versioned `/api/v2/qx/opportunities` list and detail endpoints.

## Source of Truth

```text
point-in-time provider context
        |
        v
qx.pipeline.orchestrator.run_pipeline()
        |
        +--> QXEvaluationResult returned to caller
        |
        +--> OpportunityPublisher.project_verbatim(result, provenance)
                  |
                  +--> immutable opportunity_evaluations row

Today / Opportunities / Trade
        |
        +--> OpportunityQueryService only
```

The publisher is downstream of `run_pipeline()`. It cannot call structure, regime, direction, playbook, trigger, tradeability, options, or portfolio engines.

## Architecture Questions

### A. What makes an OpportunityRecord unique?

`evaluation_id` is `qxev1_` plus a server-issued UUIDv7 lowercase-hex identifier. Duplicate prevention uses `qxcmd1_` plus SHA-256 of a canonical environment/producer/run/symbol/timeframe command manifest, reserved before provider acquisition or `run_pipeline()`. Live evaluation time is established after acquisition and enters the input fingerprint, not the command key. Input and result digests detect conflicts. Evaluation identity is stable after persistence and independent of DTO serialization changes.

### B. What does one record represent?

One record is one completed canonical evaluation invocation. It is not a setup lifecycle and not a stream. A stream key is only a query grouping. BE1 must not fabricate setup identity because Phase 6 has no stable cross-evaluation setup ID.

### C. How do repeated evaluations behave?

- Completed idempotency key: return the existing record without reacquiring data or rerunning.
- Reserved/in-progress key: return in-progress/conflict without rerunning.
- Failed/indeterminate key: quarantine for reconciliation; never automatically rerun under the same key.
- Intentional reevaluation: use a new idempotency key and create a new immutable record.
- Corrected evaluation may set `supersedes_evaluation_id`; it never overwrites the prior row.

### D. How are lifecycle states represented over time?

Every record stores the exact `current_lifecycle_state` emitted by `run_pipeline()`. WATCH, ARMED, TRIGGERED, TRADEABLE, OPTIONS_SUITABLE, PORTFOLIO_APPROVED, BLOCKED, NO_SETUP, NOT_TRADEABLE, OPTIONS_NOT_SUITABLE, PORTFOLIO_VETOED, and EXPIRED remain distinct. Ordered records show observations over time without claiming one setup lifecycle.

### E. How are replay/backtest observations prevented from appearing live?

The live repository accepts only `observation_mode=LIVE`. SHADOW stays in `shadow_telemetry`; REPLAY stays in `replay_*`; RESEARCH is not eligible for the live table; FIXTURE is never persisted. Live APIs hard-code LIVE scope and accept no client mode override.

### F. How are modes distinguished?

- LIVE: emitted only by the approved service-owned live publisher.
- SHADOW: canonical comparison observation in shadow telemetry.
- REPLAY: historical point-in-time observation under a replay run.
- RESEARCH: interactive/ad hoc canonical evaluation, not live-list eligible.
- FIXTURE: test/preview only, never production persistence.

Mode is independent from `publication_state`. A LIVE observation may still be `RESEARCH_ONLY` or `BLOCKED`.

### G. What is the expiry policy?

Canonical lifecycle `EXPIRED` is stored only when emitted by `run_pipeline()`. Service visibility expiry uses `expires_at` and derived CURRENT/STALE/ARCHIVED metadata; it never rewrites lifecycle state. Records without an approved `expires_at` remain available by exact ID but fail closed from fresh current lists. TTL values by timeframe require human approval.

### H. How does Trade preserve exact identity?

Today and Opportunities link to Trade with `evaluation_id`, symbol, timeframe, and evaluation timestamp. Trade first calls detail-by-ID and verifies duplicated context. It never silently reruns when the record is missing or stale. Explicit user reevaluation remains an ephemeral RESEARCH result unless a separately approved LIVE producer owns it.

### I. How do Today and Opportunities query without recomputing?

Both call the read-only list endpoint. Reads access persisted immutable records only and invoke no provider or engine.

### J. What is stored versus referenced?

Stored: safe canonical decision projection, exact states, reasons, WHY evidence, trigger/invalidation, versions, dependency provenance, immutable input hashes, snapshot references, and integrity hashes. Referenced: raw bars, option chains, and account snapshots. The exact ordered visible bar window passed to `run_pipeline()` is canonically serialized and hashed before evaluation; the digest is stored even though raw bars are not duplicated. Credentials, tokens, raw account numbers, callback codes, account equity, buying power, and unrestricted exception strings are prohibited.

### K. What provenance is retained?

Pipeline/config/engine versions; evaluation, request, and recorded timestamps; per-dependency source, data-as-of, retrieval visibility where available, freshness, publication/sync/quality status, reason codes, cache status, safe snapshot IDs; observation mode; producer version; input fingerprint; result digest.

### L. What migrations are required?

A validated migration-zero bootstrap creates the migration ledger when absent. One additive checksummed BE1 migration then creates `opportunity_publication_commands`, `opportunity_evaluations`, and indexes plus its ledger entry. Existing shadow, replay, snapshot, canonical v2, and legacy tables remain unchanged. No historical backfill is required and no non-LIVE record is relabeled LIVE.

## Publication and Lifecycle Handling

- Preserve `publication_state` exactly: VERIFIED, RESEARCH_ONLY, SIMULATED, or BLOCKED.
- Preserve lifecycle state exactly; no repository or frontend promotion.
- Publication state controls truth/eligibility semantics but does not identify origin.
- VERIFIED and RESEARCH_ONLY records with current service visibility and progressive lifecycle states are included by default; RESEARCH_ONLY remains visibly labeled read-only.
- SIMULATED is excluded from production current lists even if retained for audit.
- BLOCKED and terminal states are excluded by default but remain retrievable through explicit approved filters.
- NO_SETUP, EXPIRED, ARCHIVED, and stale records are excluded from default current lists.
- No BE1 state implies execution eligibility.

This inclusion matrix is the recommended contract and requires human approval with the rest of the persistence model.

## Persistence Lifecycle

1. The approved producer creates a stable idempotency key.
2. Reserve that key transactionally before provider acquisition or pipeline work.
3. If the key is already completed, return its evaluation ID without rerunning.
4. Construct point-in-time-safe context and compute the visible-bar digest plus snapshot manifest.
5. Call `run_pipeline()` exactly once for the reserved command.
6. Validate result/privacy invariants and compute the result digest.
7. In one transaction, insert the immutable record and mark the command completed.
8. A crash/indeterminate command is quarantined and never retried automatically under the same key.
9. Return the persisted `evaluation_id`; query consumers read storage only.

## Persistence Choice

Use additive SQLite tables through the existing WAL connection factory. This matches current operational persistence, avoids a new vendor, and supports atomic idempotency. Human review selected `Settings.runtime_database_path`, defaulting to `data/scanner_history.db`, as the single runtime source.

## API Summary

- `GET /api/v2/qx/opportunities`: bounded LIVE-only list query.
- `GET /api/v2/qx/opportunities/{evaluation_id}`: exact immutable safe projection.
- Existing `POST /api/v2/qx/evaluate/{symbol}` remains the canonical RESEARCH evaluation command and never becomes a read path or LIVE publisher.
- A future approved publisher may evaluate a bounded universe and persist results, but it must call the same `run_pipeline()`.

## Security and Privacy

- Strict allowlisted DTO; never persist arbitrary contexts or unrestricted `QXEvaluationResult.model_dump()`.
- Require internal hashed account references if any account reference is retained.
- Never persist raw account snapshots, account numbers, balances, positions, credentials, OAuth material, callback codes, or provider secrets in opportunity payloads.
- Do not log payload JSON or rejected sensitive values.
- Bound limits and cursor validation; no arbitrary SQL sort/filter input.
- LIVE publication is a server-owned capability, not a browser parameter.

## Resolved Human Decisions

1. The immutable OpportunityRecord model and additive schema are approved.
2. `Settings.runtime_database_path`, default `data/scanner_history.db`, owns runtime persistence.
3. Opaque UUIDv7-based evaluation identities and payload-hashed idempotency are approved.
4. LIVE publication remains an internal Python capability with no browser/write API; interactive evaluation remains RESEARCH and non-persisting.
5. BE1 does not define timeframe TTL values. The approved internal producer must supply an approved future `expires_at` plus `freshness_policy_version`, or publication fails closed.
6. BLOCKED and terminal latest records suppress older actionable states; they are excluded from default display and require explicit filters.
7. Retention is non-destructive in BE1. Future archive deletion remains separately human-gated.
8. Horizon remains context-only until BE2 and is excluded from canonical identity.
9. Audited bar provenance now exposes validated content SHA-256 and retrieval time; both are mandatory for LIVE publication.
10. Commands use RESERVED, COMMITTED, and ABANDONED with TTL reconciliation and no record creation during reconciliation.

## Risks

- Treating a record as a setup lifecycle would merge unrelated evaluations.
- Letting arbitrary requests select LIVE mode would pollute production opportunities.
- Using timestamp alone would collapse corrected evaluations.
- Persisting unrestricted pipeline output could retain portfolio-sensitive data.
- Silent Trade recomputation would break exact identity.
- Automatic TTL values could introduce unapproved product semantics.
- Backfilling shadow/replay records into LIVE would contaminate opportunity feeds.
- Foreign-key behavior is not enabled by the shared connection factory, so snapshot references require explicit validation.

## Recommended Implementation Sequence After Approval

1. Add versioned domain DTOs and identity/idempotency tests. Implemented.
2. Add strict additive migrations and repository transaction tests. Implemented.
3. Add canonical `run_pipeline()` publisher adapter with privacy and point-in-time validation. Implemented; no browser write route exists.
4. Add read-only list/detail service and deterministic ETags. Implemented.
5. Migrate Today and Opportunities opportunity reads. Implemented without changing market-pulse ownership.
6. Change Trade evaluation-ID handoff to exact detail GET. Implemented; direct evaluation remains explicit RESEARCH POST.
7. Complete independent Architecture, Quant/Data Semantics, QA, and Performance review before HUMAN_REVIEW.
8. Migrate Opportunities to the same list contract.
9. Migrate Trade to exact detail lookup with explicit refresh behavior.
10. Run performance, point-in-time, full regression, preflight, UI previews, and checker gates.

## Prohibited Behavior

BE1 must not recalculate trading logic, create another signal engine, infer lifecycle state, manufacture opportunities, alter thresholds/playbooks/Phase 3-10 semantics, begin Phase 11, add broker writes, or delete legacy paths.
