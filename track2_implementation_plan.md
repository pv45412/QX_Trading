# QX Core V1 — Track 2 Parallel Stabilization Implementation Plan

## Goal and Guardrails

Implement Tracks 2A–2G as independently testable workstreams around the approved `core_v1` Phase 3–10 pipeline.

The canonical evaluation path remains:

`Structure -> Regime -> Direction -> Playbooks -> Trigger -> Tradeability -> Options Expression -> Portfolio Risk`

Non-negotiable constraints:

- Keep `qx.pipeline.orchestrator.run_pipeline()` as the only live and replay rules orchestrator.
- Do not copy Phase 3–10 business logic into UI, replay, provider, analytics, or benchmark modules.
- Do not start Phase 11, route orders, add trading permissions, or modify execution behavior.
- Do not delete legacy modules or change trading thresholds for optimization.
- Do not fabricate bars, option chains, account state, outcomes, or shadow observations.
- Preserve `pipeline_version="core_v1"` in API, replay, telemetry, provider snapshots, and reports.
- Keep the V2 UI disabled by default behind `qx_v2_ui_enabled` while legacy UI remains available.
- Preserve `request_started_at` separately from `evaluation_timestamp` for live requests.
- Use maker/checker gates for every workstream with at most three automated repair cycles.

## Repository Findings and Safe Adaptations

1. `POST /api/v2/qx/evaluate/{symbol}` already returns lifecycle state, stage outputs, reason codes, evidence summary, versions, and stage timing, but it only loads cached bars.
2. `HistoricalReplayAdapter` already calls the same `run_pipeline()` and records state transitions, but it has no observation schema, outcome calculations, segmentation, or persistence.
3. A Schwab option-chain reader exists, but it returns the older `qx.options.chains.OptionContract` model rather than `OptionsContext` and does not persist point-in-time snapshots.
4. `ReadOnlyPortfolioService` defines a safe read-only boundary, but production has no real Schwab account provider and its `PortfolioSnapshot` is not adapted to `AccountRiskContext`.
5. `shadow_telemetry` is persistent and contains one current comparison row, but no aggregate analysis API exists.
6. The React application has Node unit tests and Playwright browser tests. Frontend coverage is available and does not require adding a new test framework.
7. Cached `SPY_10d_5m.csv` data is available for the first canonical bar replay. Historical option/account snapshots are not available, so the first replay must report those downstream stages as unavailable rather than synthesize them.
8. The older future-architecture document deferred historical replay and option-chain warehousing. The newer Track 2 directive supersedes it narrowly: implement bar-by-bar replay over supplied/existing bars and store only observed canonical snapshots, not tick replay or a large historical warehouse.

## Shared Contracts

### Provider Availability

Add typed dependency metadata to the canonical result without changing engine decisions:

- dependency name: `bars`, `option_chain`, or `account_snapshot`
- source/provider
- `data_as_of`
- freshness state and age
- publication state
- sync status
- availability and blocking reason
- cache hit/miss
- external call count and elapsed milliseconds

Skipped providers remain unavailable; they are never represented as successful with zero latency.

### Replay Observation

Each evaluated bar records:

- symbol, timeframe, timestamp, session date, and `core_v1`
- publication state
- trend, volatility, gamma, and session regimes
- direction score, label, numeric coverage, and coverage status
- playbook id and lifecycle state
- trigger and invalidation values
- tradeability, options, and portfolio states when present
- reason codes, evidence summary, engine versions, and stage latencies

### Outcome Measurement

Outcome analytics are observational and do not alter canonical rules:

- `signal_r` uses `trigger_price -> invalidation_price`; it is signal excursion/outcome measurement and must never be described as an actual trade return.
- `tradeability_r` uses Phase 8 `observed_entry_reference_price -> invalidation_price` and exists only when the setup reached `TRADEABLE`.
- Invalid or zero risk produces unavailable R metrics for the affected R concept.
- Long and short excursions use direction-aware high/low prices.
- MFE and MAE are recorded in price units plus separate `signal_r` and, when eligible, `tradeability_r` multiples.
- Endpoint R is the direction-adjusted close at the deterministic measurement endpoint divided by the applicable risk unit.
- The endpoint is the first invalidation, first structural target, lifecycle termination, or session end; same-bar target/invalidation ambiguity is classified conservatively as invalidation-first and flagged.
- Time and bars to trigger start at the first ARMED observation for the setup.
- Time and bars in setup span first WATCH/ARMED observation through trigger, invalidation, or session end.
- Outcomes are `TARGET_HIT`, `INVALIDATED`, `FALSE_TRIGGER`, `NO_TRIGGER`, `OPEN_AT_SESSION_END`, or `UNMEASURABLE`.
- False-trigger rate uses triggered setups invalidated before reaching +1R MFE.
- Invalidation-before-trigger rate uses armed setups whose invalidation is crossed before a trigger.

## Track 2A — API / UI Integration

### Implementation

- Add `web/src/qx-v2-adapter.js` as a pure adapter from the canonical snake-case API payload to a defensive lifecycle view model.
- Add `web/src/useQxV2Evaluation.js` to POST the selected symbol to the canonical endpoint with abort, timeout, loading, unavailable, and retry states.
- Add `web/src/qx-v2-feature.js` with the exact `qx_v2_ui_enabled` flag, resolving runtime flags first and `VITE_QX_V2_UI_ENABLED` second; default is false.
- Mount the V2 lifecycle experience inside the existing intelligence/research surface without removing or replacing legacy cards.
- Keep V2 values nullable and render unavailable values as unavailable, never as zero.

### View Model

The adapter exposes:

- current lifecycle state and state category
- primary playbook and direction
- direction score and evidence coverage
- trigger and invalidation
- flattened reason codes
- ordered evidence ladder entries
- reached, available, skipped, and blocked status for every downstream stage
- source freshness and publication status
- total and per-stage latency

## Track 2F — Reusable Lifecycle Experience

### Implementation

- Add `web/src/QXLifecyclePanel.jsx` and focused styles in `web/src/dashboard.css`.
- Render the progressive path `WATCH -> ARMED -> TRIGGERED -> TRADEABLE -> OPTIONS_SUITABLE -> PORTFOLIO_APPROVED`.
- Render terminal branches `BLOCKED`, `NO_SETUP`, `NOT_TRADEABLE`, `OPTIONS_NOT_SUITABLE`, and `PORTFOLIO_VETOED`.
- Defensively support the existing backend `EXPIRED` state even though it is not part of the requested primary matrix.
- Add an accessible expandable `WHY?` section for reason codes and evidence ladders.
- Wrap the mounted panel in the existing `ErrorBoundary` and preserve the current design tokens and responsive layout.

## Track 2D — Canonical Live Data Providers

### Option-Chain Provider

- Add a canonical read-only option snapshot protocol and a Schwab implementation.
- Perform one chain request per evaluation, map actual contract symbols, quotes, IV, Greeks, multiplier provenance, quote timestamps, and events into `OptionsContext`.
- Record `source`, `data_as_of`, freshness, publication state, sync status, retrieval time, and provider errors.
- Persist successful snapshots before use; never persist a fabricated empty chain as available.

### Account Provider

- Add a Schwab read-only account provider under the existing read-only portfolio boundary.
- Fetch balances and positions without exposing any order method.
- Hash account identifiers and map balances, positions, Greeks, sector allocations, freshness, and sync status into `AccountRiskContext`.
- Set `read_only=True` unconditionally in the canonical adapter.
- Return unavailable/blocked metadata when credentials, account data, or synchronization are unavailable.

### Point-in-Time Store and Context Construction

- Add a WAL-backed snapshot repository with `option_chain_snapshots` and `account_snapshots` tables.
- Store source, observed/retrieved timestamps, freshness, publication state, sync status, `core_v1`, and JSON payload.
- For an explicit historical evaluation timestamp, read only snapshots where `data_as_of <= T` and never call a live provider.
- For a live evaluation without explicit `T`, record `request_started_at`, fetch and persist provider snapshots, establish one evaluation timestamp after acquisition, then select bars and snapshots at or before that timestamp.
- Keep defensive timestamp checks in `run_pipeline()`.
- Inject providers and repositories into `create_qx_v2_router()`; provider construction is lazy and provider failures return correct partial/blocked states instead of HTTP 500.
- Never persist or log raw account numbers, OAuth/API secrets, access tokens, refresh tokens, or credentials; only hashed/internal account identifiers and required read-only risk data may enter storage.

## Track 2B — Signal Validation / Replay

### Implementation

- Keep `HistoricalReplayAdapter.replay()` as the only replay evaluation entry into `run_pipeline()`.
- Add `src/qx/pipeline/replay_analysis.py` for observation extraction, setup episode grouping, outcome measurement, and segment aggregation.
- Add `src/qx/pipeline/replay_store.py` for WAL-backed replay runs, observations, transitions, outcomes, and segment summaries.
- Persist option/account snapshot ids or provenance used by each observation.
- Add a bounded CLI/script that loads supplied cached bars and optional canonical snapshot history, invokes `HistoricalReplayAdapter`, persists results, and emits JSON/Markdown summaries.
- Run the first replay against the existing SPY 10-day 5-minute cache. Report options and portfolio results as unavailable unless real point-in-time snapshots exist.
- Treat missing historical option/account snapshots as a valid partial replay: upstream Phase 3–8 observations remain measurable and downstream stages remain explicitly unavailable/skipped.

### Segments

Aggregate counts and outcome metrics by:

- playbook
- trend market regime
- direction label
- evidence coverage bucket/status
- session regime
- volatility regime

No segment changes thresholds or feeds optimization back into the engine.

Any proposed direction, playbook, RVOL, risk/reward, options, or portfolio-risk threshold change is reported only as a research finding with `HUMAN_REQUIRED`; Track 2 never applies it automatically.

## Track 2E — Shadow Analysis

### Implementation

- Extend `ShadowTelemetryRepository` with bounded, read-only query methods.
- Add `src/qx/pipeline/shadow_analysis.py` for deterministic aggregate analysis over only the configured approved symbols.
- Report total comparisons, agreement rate, state mismatch counts, direction mismatch counts, legacy-signal/V2-no-setup, legacy-no-signal/V2-setup, error mismatches, and legacy/V2 latency distributions.
- Preserve raw classifications and sample sizes; do not label either engine correct.
- Treat the current single stored row as an insufficient-sample baseline rather than extrapolating.

## Track 2C — Performance Baseline

### Backend

- Preserve existing real per-stage timers and add typed per-operation I/O metrics.
- Record endpoint elapsed time, `total_ms`, external I/O, cache hit/miss counts, provider calls, snapshot-store timing, and SQLite busy/error observations.
- Add a non-gating benchmark runner that reports p50/p95/p99 for cached evaluation and, when credentials/data are available, live external-data evaluation.
- Count repeated provider/storage operations by operation key to identify duplicate calls without introducing caching architecture.
- Compare results with provisional research budgets: cached p95 under 300 ms and live p95 under 1000 ms.

### Frontend

- Add lightweight development/test instrumentation using browser Performance APIs and React Profiler around the new lifecycle component.
- Measure initial route load, ticker switch, scanner refresh, lifecycle render count, chart redraw count, memory when Chromium exposes it, duplicate API calls, and observed polling frequency.
- Add a Playwright baseline runner that writes a machine-readable artifact and does not fail CI solely for provisional budget misses.
- Compare local interactions with the provisional perceived-response budget of 100 ms.

## Track 2G — Legacy Migration Readiness

- Update `migration_matrix.md` from Track 1 observations to actual Track 2 usage.
- Use only `KEEP`, `WRAP`, `ADAPT`, or `DEPRECATE`; never use `REMOVE`.
- Explicitly cover `src/qx/signals/`, `src/qx/options_scanner/`, `src/qx/market/regime.py`, `src/qx/market/ai_review.py`, and `src/qx/execution/`.
- Keep legacy scanner logic isolated to V1/shadow comparison and keep `src/qx/execution/` at `ADAPT / REVIEW` with no behavior changes.

## Expected File Impact

### Canonical Backend

- Modify `src/qx/pipeline/models.py`, `adapters.py`, `shadow_telemetry.py`, and point-in-time helpers only for additive contracts and analytics support.
- Add `src/qx/pipeline/providers.py`, `snapshot_store.py`, `replay_analysis.py`, `replay_store.py`, `shadow_analysis.py`, and `performance.py` as focused modules.
- Add `src/qx/brokers/schwab/accounts.py` and adapt the existing Schwab option provider/factory without importing legacy signal logic.
- Modify `src/qx/interfaces/qx_v2.py` for provider-aware point-in-time context construction and `src/qx/interfaces/web.py` only for dependency wiring.

### Frontend

- Add the adapter, feature flag resolver, data hook, lifecycle panel, and performance helper under `web/src/`.
- Modify `web/src/QXTradingSuite.jsx`, `web/src/dashboard.css`, and `web/package.json` narrowly.
- Do not redesign unrelated routes or all eight pages.

### Reports and Migration

- Add `scripts/run_track2_replay.py` and `scripts/run_track2_baseline.py`.
- Add `track2_report.md` with all sixteen requested deliverable sections and generated result references.
- Update `migration_matrix.md` without deleting legacy code.

## Test Plan

### Unit and Contract Tests

- Python: provider mapping/failure behavior, point-in-time snapshot visibility, replay observations/transitions/outcomes, MAE/MFE/R calculations, segmentation, shadow aggregates, and performance statistics.
- API: V2 provider injection, live versus historical source selection, unavailable-provider blocking, additive result metadata, and preservation of `core_v1`.
- Frontend Node tests: all lifecycle mappings, feature flag on/off behavior, evidence ladder flattening, reason codes, unavailable numeric values, and downstream stage availability.
- Browser tests: panel loading/error/retry, all requested terminal states via route fixtures, WHY expansion, ticker switching, responsive layouts, no overflow, and no console errors.

### Required Verification Order

1. Run focused Track 2 Python and frontend unit tests.
2. Run applicable API/integration tests.
3. Run `npm test` and `npm run build` in `web/`.
4. Run Playwright lifecycle/performance tests at 1440, 1024, 768, and 375 pixel widths.
5. Run `\.\.venv\Scripts\pytest.exe tests/unit/ -ra` exactly as the full unit regression.
6. Run `\.\.venv\Scripts\pytest.exe tests/integration/ -ra` and applicable regression tests.
7. Run `qx.tools.run_preflight_checks` with temporary local services and stop those services afterward.

### Maker-Checker Gates

For each independently testable workstream:

1. The maker implements the bounded change and focused tests.
2. An independent architecture checker reviews architecture, causality, legacy leakage, security, and point-in-time behavior.
3. An independent quant checker reviews replay, outcome, provider-data, and trading-logic semantics where applicable.
4. An independent performance/UI checker reviews UI or performance work where applicable.
5. An independent QA gatekeeper runs focused tests and the required regression suites.
6. A checker `BLOCK` returns to the maker for repair and re-check, up to three cycles; a third failed cycle becomes `HUMAN_REQUIRED`.

The maker never approves its own implementation. Human approval is requested only for trading-rule changes, materially different architecture alternatives, new vendors, destructive migration, broker write permissions, or security/credential changes.

## Completion Criteria

- Every Track 2A–2G workstream has separate tests and a separate report section.
- Live and replay still use the single canonical `run_pipeline()`.
- Real providers are used in production paths; mocks/fixtures exist only in tests.
- The lifecycle component understands all requested states and renders evidence/reasons.
- Replay results include transitions and transparent outcome metrics without synthetic downstream data.
- Cached and available-live backend percentiles plus frontend measurements are recorded before optimization.
- Snapshot provenance and point-in-time visibility are persisted.
- Shadow findings remain observational.
- No Phase 11, automated execution, legacy deletion, Redis, WebSocket expansion, or broad UI redesign is introduced.
