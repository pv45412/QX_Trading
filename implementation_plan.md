# Track 1 Canonical Integration Implementation Plan

## Technical Goal and Requirements

Complete the Phase 3-10 canonical pipeline and expose it through API v2, historical replay, and deterministic v1 shadow comparison without starting Track 2 or Phase 11 and without deleting legacy modules.

The canonical flow is:

`Structure -> Regime -> Direction -> Playbooks -> Trigger -> Tradeability -> Options Expression -> Portfolio Risk`

Every evaluation uses one explicit UTC `evaluation_timestamp`, `pipeline_version="core_v1"`, typed stage outputs, stop-state-aware `None` downstream fields, and per-stage latency instrumentation where skipped stages are recorded as `SKIPPED`.

## Component Impact and File Demarcations

- `src/qx/pipeline/models.py`: canonical context/result contracts and version metadata.
- `src/qx/pipeline/orchestrator.py`: complete Phase 3-10 flow, stop states, point-in-time filtering, and instrumentation.
- `src/qx/pipeline/adapters.py`: historical replay through the same orchestrator with point-in-time snapshots.
- `src/qx/pipeline/shadow_telemetry.py`: SQLite WAL shadow comparison schema and persistence.
- `src/qx/interfaces/web.py`: canonical API v2 route and failure-isolated v1 shadow execution.
- `src/qx/config/rules_config.py`: typed deterministic shadow-mode configuration.
- `src/qx/config/rules_config_v1.json`: authoritative `research_v1` shadow symbol list.
- `src/qx/config/rules_config_v1.yaml`: human-readable mirror of the shadow configuration.
- `src/qx/regime/market_regime.py`: evaluation-time propagation instead of engine-local wall-clock time.
- `src/qx/options_expression/engine.py`: shared evaluation timestamp support.
- `src/qx/portfolio/portfolio_risk_engine.py`: shared evaluation timestamp and injected config support.
- `migration_matrix.md`: Track 1 migration disposition, including `src/qx/execution/ = ADAPT / REVIEW`.
- `tests/unit/test_track1_canonical_integration.py`: required pipeline, replay, API, shadow, timestamp, and telemetry tests.

## Data Schema and API Contracts

- `QXEvaluationContext` contains symbol, timeframe, explicit evaluation timestamp, point-in-time bars, quote/evidence, optional options context, optional account snapshot, config, publication state, and I/O/cache measurements.
- `QXEvaluationResult` contains typed optional stage outputs, lifecycle state, evaluation timestamp, publication state, `core_v1`, config/engine versions, reason/evidence fields, and stage latencies.
- `POST /api/v2/qx/evaluate/{symbol}` builds a point-in-time context and calls only the canonical orchestrator for evaluation.
- `HistoricalReplayAdapter.replay()` returns `QXEvaluationResult` values and never selects bars, option snapshots, or account snapshots newer than the evaluation bar.
- `shadow_telemetry` is the canonical SQLite comparison store and contains all approved identity, output, agreement, latency, error, publication, and version columns.

## Risk Drivers and Edge Cases

- No data from after `evaluation_timestamp` may enter any stage.
- Missing or stale required evidence must fail closed without constructing objects for skipped downstream stages.
- `NO_SETUP`, `WATCH`, non-triggered `ARMED`, failed tradeability, failed options suitability, and final portfolio states must stop at their exact boundaries.
- V2 or telemetry failures during shadow mode must never alter the legacy v1 response.
- Shadow eligibility must come only from versioned `EXPLICIT_SYMBOLS` configuration.
- SQLite writes must use WAL, a 10-second busy timeout, and normal synchronous mode.

## Verification

1. Run focused Track 1 unit and API integration tests.
2. Run `tests/unit/ -ra` with the repository virtual environment.
3. Run applicable integration/API tests.
4. Run `tests/regression/` when available.
5. Run `qx.tools.run_preflight_checks`; report service availability failures separately from code-test failures.

## Live Index Quote Field Availability Addendum

### Technical Goal and Requirements

Distinguish a connected broker response that does not publish a field from a failed or unavailable data connection. Preserve the source-backed SPX last value and volume while keeping absent executable bid/ask values null.

### Component Impact and File Demarcations

- `src/qx/interfaces/market_quotes.py`: publish asset type and field-level availability, source, and reason evidence.
- `web/src/qx-today-model.js`: retain field evidence in the Today presentation model.
- `web/src/QXTodayWorkspace.jsx`: render `NOT PUBLISHED` for non-executable index bid/ask fields and expose the broker reason.
- Backend and frontend quote tests: verify no SPY proxy or synthetic spread is introduced.

### Data Schema and API Contracts

- Every quote value field exposes `availability`, `source`, and an optional `reason_code` under `field_evidence`.
- Missing bid/ask values on an `INDEX` are `NOT_PUBLISHED` with reason `INDEX_NO_EXECUTABLE_ORDER_BOOK`.
- Other missing values remain `UNAVAILABLE`; existing numeric fields and top-level quote status remain backward compatible.

### Risk Drivers and Edge Cases

- A live connection does not guarantee every instrument publishes every market field.
- SPX must never inherit SPY bid/ask values or a calculated synthetic spread.
- Missing equity or ETF bid/ask values must remain `UNAVAILABLE`, not be classified as an index limitation.

### Verification

1. Validate the raw Schwab `$SPX`, `SPY`, and `QQQ` quote payloads.
2. Run focused backend and frontend quote tests.
3. Run the Today browser QA test against the live app.
4. Run regression and preflight checks.
