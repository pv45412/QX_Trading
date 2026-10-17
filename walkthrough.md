# QX Track 1 Canonical Integration Walkthrough

## Implemented Architecture

- `qx.pipeline.orchestrator.run_pipeline()` is the sole Phase 3–10 orchestration entry point.
- `qx.interfaces.qx_v2` owns the legacy-free `POST /api/v2/qx/evaluate/{symbol}` route.
- `HistoricalReplayAdapter` invokes the same canonical `run_pipeline()` function.
- `qx.pipeline.point_in_time` filters bars and selects snapshots before context construction; the orchestrator repeats bar filtering defensively.
- `qx.pipeline.shadow_telemetry` owns the WAL-configured SQLite schema and writes for legacy-to-v2 comparisons.
- Legacy options-scanner shadow work runs as a FastAPI background task and cannot change the v1 response.

## Canonical Stage Flow

`Structure -> Regime -> Direction -> Playbooks -> Trigger -> Tradeability -> Options Expression -> Portfolio Risk`

Downstream stages remain absent and their latency is `SKIPPED` whenever lifecycle state or missing point-in-time input stops evaluation. Missing option-chain and account snapshots are reported as explicit blocked dependencies; no market or account data is fabricated.

## Verification Evidence

- Focused Track 1 tests: `27 passed`, `2 warnings`, `1.90s`.
- Phase 3–10 plus web/API focused suite: all Phase 3–10 tests passed; the route-order regression was corrected and revalidated.
- Integration APIs: `5 passed`, `2 warnings`, `1.78s`.
- Full unit regression: `2103 collected`, `2101 passed`, `2 skipped`, `0 failed`, `2 warnings`, `159.26s`.
- Regression suite: `18 passed`, `2 warnings`, `14.00s`.
- Live API smoke: HTTP `200`, lifecycle `NO_SETUP`, pipeline version `core_v1`, real Phase 3–6 timings, later stages `SKIPPED`.
- Final preflight with temporary local services: all `13` backend/frontend checks passed; temporary processes were stopped afterward.

## Scope Confirmation

- Track 2 was not started.
- Phase 11 was not started.
- No legacy modules were deleted.
- `src/qx/execution/` remains `ADAPT / REVIEW`.
# BE1 Human-Authorized Fail-Closed Repair

- Canonical Opportunity routes now mount only after migration and schema validation succeeds.
- Invalid migration/schema state degrades only the Opportunity service to sanitized `503`; the wider application remains available.
- Fresh evidence: 35 focused BE1 tests, 2313 maintained unit tests with 2 skips, 18 regressions, 128 frontend tests, 11 UX2 browser tests, production build PASS, and preflight PASS.
- Independent outcome: Architecture PASS; Data/Security BLOCK on undetected migration-ledger DDL drift; QA not run per stop-on-BLOCK authorization.
- BE1 returned to `HUMAN_REQUIRED`; BE2 remains frozen.

# Primary Workspace Page Repair

- Audited Today, Opportunities, Trade, Portfolio, Research, and System with settled live
  requests at desktop and mobile widths.
- Restored approved Today hierarchy, explicit cross-workspace actions, provenance labels,
  compact unavailable-driver presentation, and canonical empty-state copy.
- Preserved the newer Trade hero while restoring its canonical identity accessibility label,
  explicit Portfolio action, and approved decision-summary wording.
- Reconciled UX1–UX3 browser contracts with the current Trade hero state location.
- Frontend unit evidence: `133 passed`.
- Primary workspace browser evidence: `51 passed` across UX1–UX6.
- Production build: PASS, `2,220` modules transformed.
- Backend regression: `18 passed`, `2 warnings`.
- Final preflight: all `13` checks passed.
- Live visual QA: zero page errors, console errors, failed API responses, pending requests,
  or horizontal overflow on all six desktop/mobile captures.
- First/final screenshots and the detailed report are under `data/reports/page_repair/`.
# Opportunities Live Activation - 2026-09-17

- Reproduced the empty canonical store while live Schwab evaluations succeeded.
- Replaced stale cached discovery on Today and Opportunities with guarded live Schwab ranked movers.
- Added deterministic audited-bar hashes and idempotent live evaluation publication.
- Added a bounded eight-symbol `Evaluate live movers` workflow with progress, explicit ACTIVE/ALL lifecycle filtering, and Trade handoff.
- Live QA persisted nine SWING evaluations; all were truthfully classified `NO_SETUP` rather than presented as missing data or promoted to opportunities.
- Visual evidence: `data/reports/full_page_activation/opportunities-live-functional.png`.
- Validation: frontend build; 139 frontend unit tests; UX1-UX6 52 browser tests; 2,375 backend unit tests with 2 skipped; 18 regression tests; 19/19 preflight checks; 40 live route/viewport audits with zero failures.

# Full Page Defect Sweep - 2026-09-17

- Re-audited all six primary workspaces across 20 route/state combinations at desktop and mobile widths.
- Replaced the static scanner document title with canonical route-aware QX Platform titles.
- Connected live trade evaluation to audited `1h`, daily, and weekly context according to the DAY/SWING/INVEST matrix.
- Derived weekly context only from audited daily Schwab evidence and excluded incomplete weeks point-in-time.
- Corrected the Trade HTF availability field, weighted score display, and displayed setup/HTF/macro labels.
- Live SOXL evidence now reports available HTF and macro dependencies for all horizons without manufacturing downstream trade decisions.
- Validation: frontend build; 140 frontend unit tests; UX1-UX6 52 browser tests; 2,377 backend unit tests with 2 skipped; 18 regression tests; 19/19 preflight checks; 40 live route/viewport audits with zero failures.

# Live Mover Enrichment - 2026-09-17

- Enriched Schwab mover rows with company identity and sector/industry from the refreshed
  symbol metadata cache, plus live price, one-day return, and SPY-relative return.
- Preserved separate provenance for mover, metadata, and benchmark evidence and kept all
  missing-source behavior fail-closed.
- Verified all 10 rendered rows expose resolved mover fields with no `UNAVAILABLE` values.
- Validation: frontend build; 141 frontend unit tests; 12 Opportunities browser tests;
  1 live Opportunities end-to-end test; 2,379 backend unit tests with 2 skipped;
  18 regressions; and 40 live route/viewport audits with zero failures.
- The initial enrichment preflight was 18/19 because Schwab daily SPY history ended at
  2026-09-16; the cross-workspace current-data repair below resolves that provider lag safely.

# Cross-Workspace Current Data And Field Evidence - 2026-09-17

- Added a fail-closed daily completion path that converts only a complete, audited Schwab
  30-minute regular session into the missing daily OHLCV bar.
- Restored current INVEST evaluations with September 17 evidence and preserved explicit
  `schwab:daily+30m->1d` provenance.
- Added visible and machine-checkable source, as-of, retrieval, and freshness evidence across
  Today, Opportunities, Trade, Portfolio, Research, and System.
- Corrected Opportunities filtered-empty messaging and daily session-date rendering.
- Validation: 141 frontend tests; 52 UX browser tests; 2,381 backend unit tests with 2 skipped;
  18 regressions; production build; 19/19 preflight; and 44 live route/viewport audits with
  zero field-source, freshness, API, console, accessibility, or overflow failures.
- Final INVEST screenshot: `data/reports/full_page_activation/opportunities-invest-current.png`.

# SPX Index Quote Availability - 2026-09-18

- Verified the raw Schwab `$SPX` response is realtime and classified as `INDEX`; it publishes
  last price, change, volume, and trade time but no executable bid or ask fields.
- Added field-level API evidence with source, availability, and reason codes for every displayed
  quote value. SPX bid/ask now report `NOT_PUBLISHED` and
  `INDEX_NO_EXECUTABLE_ORDER_BOOK` instead of a generic connection failure.
- Preserved null bid/ask values without substituting SPY or calculating a synthetic spread.
- Validation: 34 focused backend tests; 142 frontend tests; 11 Today browser tests; 18
  regressions; production build; 19/19 preflight; and 44 live desktop/mobile routes with zero failures.
- Visual evidence: `data/reports/full_page_activation/today-spx-field-evidence.png`.
