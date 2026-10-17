# QX Full-Page Activation and Value-QA Implementation Plan

## Goal

Bring the six primary QX workspaces to a reliable, source-backed live state and verify every
visible box, field, status, action, and cross-page handoff without inventing market,
portfolio, options, or opportunity data.

The implementation must preserve these boundaries:

- all brokerage access remains read-only;
- unavailable, stale, partial, blocked, and empty states remain distinct;
- a valid empty opportunity list is not converted into synthetic opportunities;
- unsupported or missing evidence never becomes a trade approval;
- historical Research evidence is not presented as a live quote;
- portfolio Greeks and sectors are populated only from approved source evidence;
- existing user work in the dirty working tree is preserved.

## Baseline Audit

The live audit covered 20 route/state combinations across Today, Opportunities, Trade,
Portfolio, Research, and System.

- All 20 views loaded with zero page errors, console errors, failed API responses, pending
  requests, or horizontal overflow.
- Today DAY, SWING, and INVEST each rendered 45 definition-list values, but canonical
  direction/regime/volatility/session values were blocked or unavailable.
- Trade DAY, SWING, and INVEST loaded without UI faults, but most decision fields remained
  unavailable because canonical bar evidence did not publish.
- Portfolio returned a fresh read-only seven-position snapshot, but remained partial because
  sector, option-Greek, daily P/L, and open-order evidence was incomplete.
- Research loaded source-backed history, but the symbol snapshot ended on 2026-09-15.
- System loaded all views; Overview remained degraded because process memory was not verified.
- Opportunities returned a healthy canonical response with zero current qualifying records.

The machine-readable baseline is `scratch/full-page-live-inventory.json`.

## Root Causes

### Runtime Configuration

The active backend was launched with:

```text
python -m uvicorn qx.interfaces.web:create_app --factory ...
```

`create_app()` defaults `configure_canonical_providers=False`, so this launch form disables
live canonical bars, account snapshots, option snapshots, and quotes. The supported app
object, `qx.interfaces.web:app`, enables those providers. `scripts/start_qx.bat` and
`web/README.md` already use the correct app object, while the root `README.md` does not.

### Market Bars

The Schwab intraday request uses a period-only query. A direct comparison showed that this
query stopped at the prior session, while the same request with bounded `startDate` and
`endDate` returned current-session bars. This makes otherwise healthy DAY evaluations fail
closed with `NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP` or stale-bar evidence.

The canonical market-data layer accepts `1m`, `5m`, `15m`, and `1d`. The UI maps SWING to
`1h`, but Schwab rejects a native 60-minute request. SWING therefore needs an explicitly
tested 30-minute-to-1-hour session-aligned aggregation path.

Daily live acquisition exists in the Schwab provider, but canonical evaluation currently
uses live acquisition only for intraday timeframes. INVEST and Research therefore depend on
stale cache files even when the provider has a newer completed daily session.

### Today

Today already fetches canonical evaluations, quotes, health, and opportunities. Its
Positions Requiring Attention card is hardcoded to `UNAVAILABLE`, even though the canonical
portfolio endpoint returns a fresh read-only snapshot. It should consume that endpoint and
summarize only returned exception codes and freshness states.

### Opportunities

The opportunity API and store are healthy but contain no current qualifying LIVE records.
The evaluation endpoint persists option and account snapshots, but no production workflow
currently invokes `OpportunityPublisher` for the page's watch universe. The empty page is
truthful. Opportunity production is a separate workflow change, not a display repair.

### Portfolio

The broker snapshot supplies account balances, positions, current values, and unrealized
position P/L. The broker payload does not currently supply usable sector metadata, option
Greeks, or both daily P/L values. The implementation must not infer those values silently.

Safe work in this phase is limited to:

- validating every returned account and position number against the API payload;
- improving explicit evidence labels and reason-code coverage where necessary;
- using the live portfolio response for Today attention;
- testing open-order fallback behavior and all partial-state branches.

Sector enrichment and option-Greek computation remain separate human-gated domain work.

### Research

The symbol snapshot route searches cache files only. It does not request and audit current
daily provider bars, so its source-backed output can lag the most recent completed session.

### System

The memory check depends on `psutil`, but `psutil` is not declared in `pyproject.toml`.
Import failure is reported internally as an initialized check and then projected as
unavailable. The health contract should report a verified measurement or an explicit
unavailable reason, never a false success.

## Architecture and Ownership

### Data Acquisition Layer

Files:

- `src/qx/brokers/schwab/market_data.py`
- `tests/unit/test_schwab_market_data.py`

Changes:

- add bounded UTC millisecond `startDate` and `endDate` parameters to intraday requests;
- retain period/frequency validation and extended-hours behavior;
- add deterministic tests for request bounds, ordering, and current-session inclusion;
- keep provider exceptions fail-closed and credential-safe.

### Canonical Bar Quality Layer

Files:

- `src/qx/pipeline/market_data_quality.py`
- `src/qx/pipeline/multi_timeframe.py`
- `tests/unit/test_market_data_quality.py`
- `tests/unit/test_be2_multi_timeframe.py`

Changes:

- support live daily acquisition through `get_daily_bars()` with the same point-in-time
  audit and publication rules used by cached bars;
- define `1h` as a canonical derived timeframe sourced from verified 30-minute bars;
- aggregate only within a single regular-market session, preserve timezone identity, and
  reject incomplete/future buckets;
- expose observed source timeframe and derived timeframe in quality evidence;
- add tests for market open, midday, close, shortened sessions, missing intervals, and
  evaluation timestamps inside an unfinished hourly bucket.

### Canonical Evaluation API

Files:

- `src/qx/interfaces/qx_v2.py`
- `tests/unit/test_track1_canonical_integration.py`
- `tests/unit/test_market_data_quality.py`

Changes:

- route DAY, SWING, and INVEST through their supported live bar acquisition path;
- preserve historical evaluation behavior and point-in-time snapshots;
- return precise dependency reason codes for provider, timeframe, stale, and incomplete-bar
  failures;
- keep blocked publication behavior when any required evidence fails.

### Research Snapshot API

Files:

- `src/qx/interfaces/web.py`
- `tests/unit/test_ux5_research_api.py`
- `web/src/qx-research-model.test.js`
- `web/tests/ux5-research.test.cjs`

Changes:

- prefer an audited live daily provider snapshot for current Research requests;
- fall back to verified cache evidence when live acquisition is unavailable;
- report `data_as_of`, `retrieved_at`, source, and fallback status independently;
- preserve Research-only language and historical-mode semantics.

### Today Portfolio Attention

Files:

- `web/src/useTodayAttentionData.js`
- `web/src/QXTodayWorkspace.jsx`
- `web/src/qx-today-model.js`
- `web/src/qx-today-model.test.js`
- `web/tests/ux3-today.test.cjs`

Changes:

- fetch `GET /api/v2/qx/portfolio` with the existing Today request group;
- derive attention only from canonical status, freshness, and reason codes;
- distinguish no positions, no exceptions, partial evidence, stale evidence, and service
  failure;
- link all details to Portfolio rather than reproducing portfolio calculations client-side.

### System Health

Files:

- `pyproject.toml`
- `src/qx/ops/health_checker.py`
- `tests/unit/test_ux6_system_api.py`
- `web/tests/ux6-system.test.cjs`

Changes:

- declare `psutil` as a runtime dependency;
- report verified RSS memory when available;
- report an explicit unavailable/error status when measurement fails;
- test healthy, high-memory, and dependency-failure branches.

### Launch Contract and Preflight

Files:

- `README.md`
- `src/qx/tools/run_preflight_checks.py`
- `tests/regression/test_preflight_data_and_routes.py`

Changes:

- replace the provider-disabled factory launch command with `qx.interfaces.web:app`;
- add preflight checks for live-provider wiring, DAY bar recency, SWING timeframe support,
  INVEST daily-bar availability, and Research completed-session freshness;
- never print credentials, tokens, account identifiers, or raw authorization errors.

## Page-by-Page QA Matrix

### Today

Test every horizon and each market card for:

- last price, daily change, bid, ask, volume;
- direction, regime, volatility, session;
- quote source/mode/timestamp/freshness;
- bar source/data-as-of/freshness/evaluation timestamp;
- Market Driver status and reason;
- opportunity empty/populated/error states;
- portfolio attention clear/partial/stale/unavailable states;
- material health item labels, reasons, and destinations;
- Refresh and all cross-page actions.

### Opportunities

Test:

- service unavailable, canonical empty, and populated fixture states;
- search, lifecycle, horizon, freshness, and blocked-record filters;
- pagination and result count;
- every card/table fact and provenance value;
- evaluation identity handoff to Trade;
- truthful zero-result behavior with no synthetic rows.

### Trade

Test DAY, SWING, and INVEST for:

- symbol/timeframe controls and one-request refresh behavior;
- lifecycle, publication, direction, structure, trigger, invalidation, target, regime,
  tradeability, options suitability, portfolio state, and Market Driver fields;
- bar/dependency provenance, freshness, reason codes, and timestamps;
- all approved fixture lifecycle states;
- Research and Portfolio handoffs with identity preservation.

### Portfolio

Test:

- account status, read-only state, equity, cash, buying power, P/L, orders, and exposures;
- every position symbol, asset class, quantity, prices, value, P/L, concentration, sector,
  and Greek field against the API response;
- sector and Greek unavailable states without inferred values;
- attention reason codes and data-quality provenance;
- no-account, partial, stale, approved, and vetoed fixtures;
- candidate impact identity arriving from Trade.

### Research

Test:

- symbol, historical, long-term, ETF/sector, relative-strength, and options modes;
- price, structure, benchmark, period, as-of, source, and freshness values;
- completed-session freshness and cache fallback labeling;
- all selectors, tabs, charts/tables, and Trade/Portfolio handoffs;
- Research-only boundary language in every mode.

### System

Test:

- Overview component status, detail, latency, and aggregate state;
- provider credential/readiness states without exposing secrets;
- data/cache inventory and freshness labels;
- job controls, schedule status, run history, and rule provenance;
- memory healthy/degraded/unavailable branches;
- each sub-navigation action and refresh behavior.

## Automated Value Validation

Add a reusable browser audit that records every visible label/value pair per route and checks:

- the value is non-empty;
- status words are from the approved vocabulary;
- numeric values parse in their displayed units;
- timestamps parse and do not claim future freshness;
- percentages and monetary values agree with API values within display rounding;
- unavailable values have a visible source/reason contract;
- links preserve required workspace context;
- no page, console, network, accessibility-name, or overflow failures occur.

The audit will run at desktop and mobile widths and store:

- JSON field inventory;
- route/API mismatch report;
- screenshots for all primary pages and exception states;
- a final Markdown validation summary under `data/reports/full_page_activation/`.

## Deferred Human-Gated Work

These items are deliberately excluded from automatic repair in this phase:

- computing option Greeks for held contracts;
- assigning sectors when the broker provides no sector provenance;
- enabling any broker write or order operation;
- changing risk thresholds, trading rules, lifecycle semantics, or approval criteria;
- publishing opportunities from a new production universe/schedule.

If requested later, option-Greek and sector work requires a separate domain design and the
`options-pricing-and-greeks` protocol. Opportunity population requires a producer design
covering universe, cadence, idempotency, expiry, and persistence ownership.

## Implementation Sequence

1. Correct the documented/runtime backend launch contract.
2. Add bounded Schwab intraday requests and provider tests.
3. Add audited live daily acquisition.
4. Add session-safe 30-minute-to-1-hour aggregation.
5. Revalidate canonical DAY/SWING/INVEST evaluations.
6. Refresh Research from audited daily evidence.
7. Connect Today to canonical portfolio attention.
8. Correct and test process-memory health reporting.
9. Expand preflight and browser value-audit coverage.
10. Run page-by-page desktop/mobile QA and publish evidence.

## Acceptance Criteria

- Backend launches through `qx.interfaces.web:app` with live providers enabled.
- During an open regular session, DAY evaluations use current-session bars when Schwab
  supplies them; outside the session they use the latest valid completed bar.
- SWING evaluations use explicitly identified, session-aligned derived `1h` bars.
- INVEST and Research use the latest valid completed daily session when available.
- Today portfolio attention reflects the canonical portfolio response rather than a
  hardcoded unavailable card.
- System memory status is verified or explicitly unavailable with a reason.
- Empty opportunities remain a valid empty state unless a separately approved producer is
  implemented.
- Portfolio fields match source payloads; unsupported sectors and option Greeks remain
  clearly unavailable.
- Frontend unit tests, UX1 through UX6, production build, backend targeted tests, regression
  tests, and preflight all pass.
- Every visible label/value pair in all 20 route/state combinations is inventoried and
  checked against its API or approved fixture source.
- Desktop and mobile runs have zero page errors, console errors, failed API requests,
  unlabeled interactive controls, and horizontal overflow.

## Human Approval Gate

Implementation begins only after explicit approval of this plan. Approval authorizes the
source and test changes listed above, but does not authorize deferred option-Greek, sector
inference, broker-write, trading-rule, or opportunity-producer changes.
# Opportunities Live Activation Addendum

## Technical Goal
- Replace stale cached discovery rows with the existing same-origin Schwab ranked-movers feed.
- Persist successful audited live evaluations into the canonical opportunity store.
- Add a bounded, explicit scan action; never manufacture lifecycle states or trade scores.

## Component Impact
- `src/qx/pipeline/market_data_quality.py`: attach a deterministic SHA-256 to audited live bars.
- `src/qx/opportunities/repository.py`: allow failed reservations to be abandoned immediately.
- `src/qx/interfaces/qx_v2.py`: reserve, evaluate, and publish live canonical evaluations idempotently.
- `src/qx/interfaces/web.py`: inject the live opportunity publisher.
- `web/src/qx-opportunities-client.js`: fetch live movers and evaluate a bounded symbol set.
- `web/src/QXOpportunitiesWorkspace.jsx`: add scan progress, filter recovery, and truthful empty states.

## API Contracts
- Existing `POST /api/schwab/movers` remains same-origin guarded and supplies ranked discovery only.
- Existing `POST /api/v2/qx/evaluate/{symbol}` remains read-only and now publishes an audited LIVE record when publication invariants pass.
- Repeated evaluations within the same timeframe bucket are idempotent and reuse the committed result.

## Risks And Controls
- Broker load is bounded by a small client-side scan limit and sequential requests.
- BLOCKED evaluations without validated bars remain visible in the scan summary but are not published.
- Terminal evaluations are not presented as active opportunities; the UI can reveal all evaluated outcomes explicitly.
- No Yahoo or synthetic fallback is silently substituted for Schwab data.

# Full Page Defect Sweep Addendum

## Technical Goal
- Give every workspace route an accurate browser title derived from the canonical route registry.
- Supply live trade evaluations with the higher-timeframe and macro evidence already required by the canonical horizon matrix.
- Keep every added value source-backed, point-in-time safe, read-only, and explicit when unavailable.

## Component Impact
- `web/src/main.jsx` and `web/index.html`: replace the legacy scanner title with route-aware QX Platform titles.
- `web/src/qx-v2-adapter.js`: map canonical HTF factor availability from the current API field.
- `web/tests/live-value-audit.cjs`: treat missing or stale route titles as a page QA failure.
- `src/qx/pipeline/multi_timeframe.py`: aggregate audited daily bars into conservative weekly candles.
- `src/qx/interfaces/qx_v2.py`: load and reuse audited live context bars for DAY, SWING, and INVEST evaluations.
- `src/qx/pipeline/orchestrator.py`: retain acquired context provenance when publishing HTF and macro dependencies.
- Targeted unit and browser tests: verify timeframe selection, strict completion filtering, source provenance, and titles.

## Point-In-Time Contract
- DAY uses audited `5m` setup bars, session-aligned derived `1h` HTF bars, and audited daily macro bars.
- SWING uses derived `1h` setup bars, audited daily HTF bars, and weekly bars aggregated only from audited daily evidence.
- INVEST uses audited daily setup bars and weekly HTF/macro bars derived from that same audited daily evidence.
- Weekly candles are timestamped at the UTC start of their Monday-to-Friday period; the existing completion filter excludes the current incomplete week.
- Failed context acquisition remains unavailable and never falls back to fabricated, cross-timeframe, or silently stale values.

## Risks And Controls
- Per-evaluation provider calls are cached by timeframe so shared daily evidence is fetched once.
- Weekly aggregation performs OHLCV-only deterministic reduction and preserves no future daily bars.
- The existing lifecycle engine remains authoritative; HTF context informs direction but does not force a tradeable state.
- A publication version bump prevents a previously committed no-HTF result from masking the corrected live evaluation in the same bucket.

# Live Mover Enrichment Addendum

## Technical Goal
- Replace unavailable mover company, sector, industry, and SPY-relative fields with source-backed values.
- Preserve the legacy-discovery boundary: enriched movers remain discovery context and never receive canonical lifecycle claims.

## Data Contract
- Schwab mover rows remain authoritative for symbol, description, last price, net change, one-day percent move, volume, trades, and market share.
- The local symbol metadata cache supplies company name fallback, GICS sector, and industry; unknown metadata remains unavailable.
- A live Schwab SPY quote supplies the benchmark one-day return.
- `SPY excess` is the deterministic mover return minus the same-request SPY return.
- Every enriched row publishes separate mover, metadata, and benchmark provenance fields.

## Component Impact
- `src/qx/brokers/schwab/movers.py`: normalize direct Schwab fields and apply bounded metadata/benchmark enrichment.
- `src/qx/interfaces/web.py`: inject the app metadata store and Schwab quote provider into the guarded mover route.
- `web/src/qx-opportunities-model.js`: preserve enrichment fields without canonical inference.
- `web/src/QXOpportunitiesWorkspace.jsx`: display industry and benchmark provenance alongside the resolved values.
- Backend, model, and browser tests verify missing-data behavior and live field population.

## Risks And Controls
- No sector is inferred from symbol, price behavior, or ETF association.
- A failed SPY quote leaves excess return unavailable rather than using stale or cross-source data.
- Metadata cache misses remain explicit; the request does not block on an unbounded external metadata crawl.
- The endpoint stays read-only and same-origin guarded.

# Cross-Workspace Current Data And Field Evidence Addendum

## Technical Goal
- Make every primary workspace render only source-backed current values or an explicit
  unavailable/blocked state.
- Attach visible source, data-as-of, retrieval, and freshness evidence to every market,
  canonical-evaluation, account, research, and operational field group.
- Restore INVEST evaluations when Schwab publishes a complete regular session through
  intraday history before its daily-history endpoint publishes that session.

## Current-Data Contract
- Direct Schwab daily candles remain the preferred INVEST source.
- When the latest completed NYSE session is absent from the daily response, audited Schwab
  regular-session 30-minute candles may deterministically complete that daily OHLCV bar.
- A derived daily bar requires all 13 regular-session half-hour candles, ordered unique
  timestamps, and a session that is complete at the evaluation timestamp.
- The merged result identifies both inputs as `schwab:daily+30m->1d`; incomplete sessions,
  missing intervals, provider failures, or non-session dates remain blocked.
- Quote, bar, benchmark, account, metadata, research, and system values retain their own
  source and timestamp; no page-level timestamp is reused as evidence for a different field.

## Component Impact
- `src/qx/pipeline/market_data_quality.py`: validate and append completed Schwab intraday
  sessions when the daily endpoint lags.
- `src/qx/interfaces/*`: preserve publication state, source, data-as-of, retrieved-at, and
  freshness in workspace responses.
- `web/src/QX*Workspace.jsx` and workspace models: render explicit evidence beside field
  groups without treating cache age as market freshness.
- `web/tests/live-value-audit.cjs`: assert every live data region exposes source and
  freshness evidence and reject stale values presented as current.
- Focused unit, browser, live-route, regression, build, and preflight checks verify the
  complete contract.

## Risks And Controls
- Intraday aggregation never fills gaps, extrapolates prices, or includes extended-hours
  bars.
- Current-session candles are excluded until the regular session is complete.
- Historical/research evidence remains labeled historical and is not promoted to live.
- Canonical lifecycle outcomes remain engine-owned; current data does not force an
  opportunity or tradeable decision.
- Broker and account paths remain read-only.

## Approval
- The user's explicit request to fix all pages, connect every field to its source, and
  ensure current data authorizes this addendum and its automated verification scope.
