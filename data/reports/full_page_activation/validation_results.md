# QX Full-Page Activation Validation

Date: 2026-09-17

## Live Outcomes

- Today DAY renders source-backed SPX, SPY, and QQQ quotes plus canonical direction,
  regime, volatility, and session context.
- Today SWING uses session-aligned hourly bars derived from audited 30-minute Schwab bars.
- Today INVEST uses the latest completed daily Schwab session.
- Today Positions Requiring Attention uses the canonical read-only portfolio response and
  reports the current seven-position partial-evidence state.
- Research uses audited daily provider evidence through the latest completed session.
- System verifies process memory and reports healthy operational status.
- Opportunities remains a truthful empty LIVE result because no qualifying canonical
  opportunity records currently exist.
- Portfolio remains truthfully partial where the broker does not supply sector provenance,
  held-option Greeks, or complete daily P/L evidence.

## Automated Results

- Frontend unit tests: 140 passed.
- UX1 through UX6 browser tests: 52 passed.
- Backend unit tests: 2,377 passed, 2 skipped.
- Backend regression tests: 18 passed.
- Production frontend build: passed.
- Live value audit: 40 desktop/mobile route combinations, 0 failures.
- Preflight: 19 checks passed, including DAY, SWING, INVEST, Research freshness,
  read-only Portfolio, and process-memory verification.

## Live Value Audit

The reusable audit is `web/tests/live-value-audit.cjs` and runs with:

```powershell
cd web
npm run test:live-values
```

It verifies:

- every visible definition-list and metric label has a non-empty value;
- every visible interactive control has an accessible name;
- API responses do not fail;
- page and console errors are absent;
- every rendered section/card has content;
- desktop and mobile pages have no horizontal overflow.
- every route publishes a canonical `QX Platform | ...` browser title.

Machine-readable results are in `live-value-audit.json` and
`live-value-audit-summary.json`. Screenshots for all 40 route/viewport combinations are in
the `screenshots` directory.

## Truthful Remaining Unavailable Evidence

- SPX is a calculated index, and Schwab's live `$SPX` payload does not publish executable
  bid/ask fields. The UI now labels both fields `NOT PUBLISHED` with source-backed reason
  `INDEX_NO_EXECUTABLE_ORDER_BOOK`; it does not substitute SPY or fabricate a spread.
- Canonical Opportunities can remain empty when no current records qualify.
- Portfolio sector allocations and held-option Greeks remain unavailable without approved
  source evidence; no values are inferred.
# Opportunities Live Activation - 2026-09-17

- Live Schwab ranked discovery: PASS
- Audited live evaluation publication: PASS
- Idempotent repeat evaluation: PASS
- ACTIVE, ALL, terminal, direction, sort, and search controls: PASS
- Canonical Opportunities to Trade identity handoff: PASS
- Live scan result: 9 persisted SWING evaluations, all `NO_SETUP`
- Frontend build: PASS
- Frontend unit tests: 139 passed
- UX1-UX6 browser tests: 52 passed
- Backend unit tests: 2,375 passed, 2 skipped
- Regression tests: 18 passed
- Preflight: 19/19 passed
- Live value audit: 40 routes, 0 failures
- Screenshot: `data/reports/full_page_activation/opportunities-live-functional.png`

# Full Page Defect Sweep - 2026-09-17

- Added route-aware browser titles and made stale legacy titles a live-audit failure.
- Activated audited HTF and macro evidence for DAY, SWING, and INVEST evaluations.
- Added point-in-time-safe weekly OHLCV aggregation from audited Schwab daily bars.
- Preserved Schwab provenance through canonical HTF and macro dependency output.
- Corrected Trade HTF availability mapping, score-point formatting, and canonical timeframe labels.
- Synchronized Trade horizon buttons with their setup timeframes.
- Live SOXL verification: DAY `WATCH`; SWING and INVEST `NO_SETUP`; all three report available HTF and macro evidence.
- Final frontend unit tests: 140 passed.
- Final backend unit tests: 2,377 passed, 2 skipped.
- UX1-UX6 browser tests: 52 passed.
- Regression tests: 18 passed.
- Preflight: 19/19 passed.
- Final live value audit: 40 desktop/mobile routes, 0 failures.
- Final screenshots: `data/reports/full_page_activation/screenshots/`.

# Live Mover Enrichment - 2026-09-17

- Verified Market Movement now resolves company name, sector, industry, last price,
  one-day return, SPY excess return, source, and data timestamp for all 10 live rows.
- Company classification comes from the refreshed source-backed symbol metadata cache;
  movement and benchmark values come from live Schwab responses.
- Missing metadata or benchmark evidence remains explicitly unavailable; the UI does not
  synthesize classifications or returns.
- Focused backend mover tests: 13 passed.
- Frontend opportunity model/client tests: 21 passed.
- Opportunities browser QA: 12 passed.
- Live Opportunities end-to-end QA: 1 passed, with 10 rows and no unavailable enriched fields.
- Final frontend unit tests: 141 passed.
- Final backend unit tests: 2,379 passed, 2 skipped.
- Regression tests: 18 passed.
- Production frontend build: passed, 2,220 modules transformed.
- Final live value audit: 40 desktop/mobile routes, 0 failures.
- Current preflight: 19 of 19 passed after completed September 17 Schwab 30-minute
  regular-session bars were audited and deterministically aggregated into the lagging daily feed.
- Screenshot: `data/reports/full_page_activation/opportunities-live-functional.png`.

# Cross-Workspace Current Data And Field Evidence - 2026-09-17

- INVEST setup bars now prefer Schwab daily history and use a guarded
  `schwab:daily+30m->1d` completion only when all 13 regular-session half-hour candles exist.
- Every primary workspace exposes visible field-group source, data-as-of, retrieval, and
  freshness evidence, with machine-checkable evidence ownership for rendered metrics.
- Opportunities now distinguishes ACTIVE-filter emptiness from an empty canonical store and
  provides `Show all evaluations` or `Clear filters` as appropriate.
- Daily session labels remain on their exchange session date instead of shifting to the prior
  evening in America/New_York.
- Live INVEST verification: 12 canonical rows visible, 0 `STALE_BARS`, source
  `schwab:daily+30m->1d`, data as of 2026-09-17.
- Frontend unit tests: 141 passed.
- UX1 through UX6 browser tests: 52 passed.
- Backend unit tests: 2,381 passed, 2 skipped.
- Backend regression tests: 18 passed.
- Production frontend build: passed, 2,221 modules transformed.
- Preflight: 19 of 19 passed, including DAY, SWING, INVEST, Research, Portfolio, and memory.
- Field/source live audit: 44 desktop/mobile route combinations, 0 failures.
- Visual evidence: `data/reports/full_page_activation/opportunities-invest-current.png`.

# SPX Index Quote Availability - 2026-09-18

- Raw Schwab identity: `$SPX`, `assetMainType=INDEX`, `realtime=true`.
- Published raw fields: last `7637.76`, change `0.0`, volume `2,922,855,343`, and trade time.
- Raw bid/ask fields: absent; API values remain null.
- API field evidence: bid and ask `NOT_PUBLISHED`, source `schwab`, reason
  `INDEX_NO_EXECUTABLE_ORDER_BOOK`.
- Live Today rendering: both fields display `NOT PUBLISHED`; expanded provenance exposes
  asset type, source, availability, and reason.
- Focused backend tests: 34 passed.
- Frontend tests: 142 passed.
- Today browser QA: 11 passed, including deterministic SPX field-availability coverage.
- Backend regressions: 18 passed in isolation. A parallel build/browser/regression attempt
  temporarily exceeded three unrelated latency thresholds; the isolated rerun passed all 18.
- Production frontend build: passed, 2,221 modules transformed.
- Live field/source audit: 44 desktop/mobile routes, 0 failures.
- Preflight: 19 of 19 passed.
- Console/page errors during live SPX capture: 0.
- Screenshot: `data/reports/full_page_activation/today-spx-field-evidence.png`.
