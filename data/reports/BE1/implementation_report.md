# BE1 Implementation Report

## Maker Scope

- Added immutable LIVE OpportunityRecord persistence and strict checksummed migrations.
- Added RESERVED, COMMITTED, and ABANDONED publication-command handling.
- Added canonical `run_pipeline()` publisher coordination with validated bar provenance.
- Added read-only list/detail APIs with exact-response strong ETags.
- Migrated Today and Opportunities opportunity reads and Trade evaluation-ID reads.
- Preserved direct interactive evaluation as non-persisting RESEARCH behavior.

## Database

- Typed source: `Settings.runtime_database_path`.
- Default: `data/scanner_history.db`.
- No opportunity-specific database is created.
- Missing legacy runtime databases remain untouched by read-only app construction.

## UI Preview

- First and final desktop/mobile evidence: `data/reports/BE1/preview/`.
- Visual repair: live empty-state copy no longer describes LIVE results as fixtures.
- Browser console errors: none.

## Performance

- Dataset: 500 immutable evaluations across 50 streams; 300 iterations.
- Results: `data/reports/BE1/performance.json`.
- Observational only; no caching or architecture optimization was introduced.

## Governance

- Phase 3-10 semantics, thresholds, playbooks, Market Driver, execution, and broker writes are unchanged.
- BE2 remains frozen.
- BE1 is `HUMAN_REQUIRED` after the Data/Security Checker found undetected migration-ledger DDL drift; QA did not run and BE2 remains frozen.

## Architecture Repair Cycle 2

- Normalized trusted LIVE list envelopes before frontend projection so actual API rows reach Today and Opportunities without weakening non-LIVE rejection.
- Added server-side consumer filters and cursor-based Opportunities pagination.
- Revalidated complete immutable records on list/detail reads; schema or digest drift now returns `409`, while store outages remain `503`.
- Split publication into pre-acquisition reservation and downstream publication of a completed canonical result; the publisher no longer invokes `run_pipeline()`.
- Bound `bar_window_sha256` to the same point-in-time filtered bar window evaluated by the canonical pipeline.
- Corrected explicit blocked queries so the latest BLOCKED stream head is returned without resurrecting older records.

## Architecture Repair Cycle 3

- Removed the reintroduced orchestration wrapper from `OpportunityPublisher`; the class now only reserves commands and persists already-completed canonical results.
- Canonicalized the point-in-time bar window into stable ascending order before any pipeline stage and made the digest preserve that exact evaluated order.
- Required publisher verification of the pipeline-emitted evaluated-window digest.
- Added evaluated bar count plus first/last bar timestamps to the input fingerprint.
- Locked list items to explicit item-level LIVE origin and updated actual-shape consumer/browser fixtures accordingly.
- Updated the performance evidence generator to satisfy the final immutable identity and projection-integrity contract.

## Human-Authorized Fail-Closed Repair

- Replaced unconditional canonical Opportunity router registration with validation-gated registration.
- Valid migration ledger, checksums, tables, indexes, and schema mount the normal read-only router.
- Missing stores mount an unavailable router with `OPPORTUNITY_STORE_UNAVAILABLE`.
- Migration or schema integrity failure mounts an unavailable router with `OPPORTUNITY_STORE_SCHEMA_INVALID`.
- The unavailable router never calls repository list/detail methods and exposes no SQL, filesystem, or exception details.
- The wider application remains available in degraded mode; canonical Opportunity list/detail endpoints return deterministic `503`.
- No OpportunityRecord, publisher, fingerprint, lifecycle, query, trading, or threshold semantics changed.

## Additional Repair Checker Outcome

- Architecture Checker: PASS.
- Data/Security Checker: BLOCK because exact DDL validation excludes the migration ledger itself; altered ledger DDL with identical columns and checksums can still enable LIVE canonical reads.
- QA Gatekeeper: NOT RUN because the authorized workflow requires an immediate stop after any BLOCK.
- Final state: `HUMAN_REQUIRED`; no additional repair or BE2 work is authorized.
