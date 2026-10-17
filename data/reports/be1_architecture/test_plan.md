# BE1 Test Plan

## Domain and Identity

- Opaque evaluation ID is stable after persistence.
- Live command reservation does not require or predate the post-acquisition evaluation timestamp.
- Same idempotency key and same digests returns one record.
- Same key and different digest fails closed.
- Completed command retry returns before provider or pipeline invocation.
- Reserved or indeterminate command never reruns automatically.
- Intentional reevaluation creates a distinct ID.
- Corrected evaluation preserves supersession lineage.
- Horizon context does not alter canonical identity.
- Null, zero, false, and empty string remain distinct.

## Persistence

- Immutable payload cannot be updated.
- Insert is atomic and rollback-safe.
- Concurrent writers produce one record per idempotency key.
- Late records preserve deterministic ordering.
- Database busy handling is bounded.
- Migrations are additive, explicit, and repeatable.
- Fresh database bootstraps and validates the migration ledger before applying BE1.
- Existing valid ledger with no BE1 row applies BE1 once.
- Existing BE1 row with the same checksum is an idempotent no-op that does not replay DDL.
- Migration checksum mismatch and unledgered pre-existing objects fail closed.
- Migration ledger schema mismatch fails closed.
- Interrupted transactional migration leaves neither partial schema nor ledger row.
- Existing tables remain byte/schema compatible.

## Point-in-Time and Freshness

- Query as-of T cannot see evaluations recorded after T.
- Dependency data-as-of and retrieval visibility remain no later than evaluation time.
- Future dependency provenance is rejected.
- Bar records without validated retrieval time/content hash cannot publish LIVE.
- Mutating bar content without changing `data_as_of` changes the bar digest and input fingerprint.
- Bar-window digest is stable across equivalent canonical serialization.
- Missing expiry excludes a record from fresh lists.
- Service staleness never rewrites lifecycle EXPIRED.
- Pipeline-emitted EXPIRED round-trips exactly.

## Mode Isolation

- LIVE repository rejects SHADOW, REPLAY, RESEARCH, and FIXTURE.
- Live API accepts no mode override.
- Shadow and replay rows never appear in live queries.
- Fixtures are never persisted.
- Interactive research cannot publish LIVE without internal capability.

## State and Publication Semantics

- Every lifecycle state round-trips exactly.
- Every publication state round-trips exactly.
- VERIFIED and RESEARCH_ONLY progressive/current records follow the default inclusion matrix.
- SIMULATED, BLOCKED, and terminal records remain excluded unless explicitly authorized.
- Terminal states remain distinct.
- No state promotion occurs from field presence.
- No response exposes execution eligibility.

## API and Consumers

- List filtering, bounds, stable cursor pagination, and cursor validation.
- Detail returns the exact requested ID.
- Missing detail returns 404 with zero pipeline calls.
- Store outage returns 503 without legacy/fixture fallback.
- Repeated reads invoke zero provider/pipeline calls.
- Today and Opportunities issue no evaluation POSTs for opportunity reads.
- Trade with an ID issues one detail GET and zero evaluation POSTs.
- Explicit reevaluation issues one RESEARCH POST and produces no LIVE persisted identity.
- Context mismatch fails visibly.
- Legacy results never expose canonical lifecycle fields.

## Security and Privacy

- Raw account numbers, account balances, positions, tokens, credentials, paths, callback codes, and unrestricted exceptions are absent from storage/API/logs.
- Only internal hashed account references are allowed.
- Filter values cannot inject SQL.
- Cursor tampering fails closed.
- DTO projection is allowlisted.
- Every OpportunityDecisionV1 field preserves null/zero/false/empty-string semantics.
- Excluded portfolio-sensitive fields cannot enter stored JSON or detail responses.

## Regression and Performance

- Canonical pipeline golden-output parity.
- Shadow/replay isolation regression.
- Today, Opportunities, Trade, Portfolio, Research, and System compatibility suites.
- Full maintained unit suite and preflight.
- List/detail p50, p95, p99 and query-plan evidence.
- Concurrent read/write tests under SQLite WAL.
- First/final/major-state desktop/mobile previews for each UI migration slice.

## Required Checker Gates After Implementation

- Architecture Checker
- Quant/Data Semantics Checker
- Security/Data Governance Checker
- QA Gatekeeper
- Performance/UI Checker where consumer UI changes occur

Any semantic, persistence, security, or architecture deviation returns to HUMAN_REVIEW.
