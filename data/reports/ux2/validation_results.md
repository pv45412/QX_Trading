# QX UX Implementation Phase 2 Validation

## Scope

Implemented only the approved canonical Opportunities destination. Today, Portfolio, Research consolidation, Market Driver, persistence, Phase 11, trading rules, thresholds, broker writes, and legacy deletion remain unchanged.

## Canonical Opportunity Data Flow

The repository has no server-owned canonical opportunity-list endpoint. The live page therefore publishes `CANONICAL DATA UNAVAILABLE` and does not manufacture candidates from movers, scanner scores, or client heuristics.

Deterministic review flow:

`explicit runtime fixture flag -> approved V2 fixtures -> qx-v2-adapter -> qx-opportunities-model -> QXOpportunitiesWorkspace`

Future live flow remains:

`server-owned opportunity record -> shared qx-v2-adapter -> qx-opportunities-model -> QXOpportunitiesWorkspace`

The presentation model copies canonical lifecycle, direction, playbook, trigger, invalidation, tradeability, options, portfolio, coverage, publication, dependency, and evaluation fields. It creates no trading score or threshold.

## Horizon Behavior

- One Opportunities destination supports `DAY`, `SWING`, and `INVEST`.
- Horizon is navigation/filter context only.
- The browser does not rescore, rename, or reinterpret lifecycle states by horizon.
- Default presentation timeframes are `5m`, `1h`, and `1d`; changing horizon clears stale evaluation timestamp/identity context.

## Trade Handoff

Canonical rows preserve symbol, horizon, timeframe, evaluation timestamp, and evaluation identity when supplied. Trade fixtures render the same handed-off timeframe and identity. Legacy rows intentionally clear evaluation timestamp/identity and request a fresh canonical Trade evaluation.

Trigger confirmation fails closed: a canonical TriggerEvent ID, event timestamp, confirmation method, and triggered state are required before the frontend displays `CONFIRMED`.

## Legacy Source Labeling

Verified `/api/movers/sp500` data appears in a separate `LEGACY SOURCE` section as market-movement discovery context only. Legacy rows contain no canonical lifecycle, trigger, tradeability, options, portfolio, or generated score fields. All 22 legacy routes and 12 aliases remain registered.

## Files Changed

- `ux2_implementation_plan.md`
- `web/package.json`
- `web/src/QXOpportunitiesWorkspace.jsx`
- `web/src/QXLifecyclePanel.jsx`
- `web/src/QXTradeWorkspace.jsx`
- `web/src/dashboard.css`
- `web/src/main.jsx`
- `web/src/qx-opportunities-client.js`
- `web/src/qx-opportunities-fixtures.js`
- `web/src/qx-opportunities-model.js`
- `web/src/qx-opportunities-model.test.js`
- `web/src/qx-v2-adapter.js`
- `web/src/qx-v2-adapter.test.js`
- `web/src/qx-v2-feature.js`
- `web/src/qx-v2-feature.test.js`
- `web/tests/ux1-trade-workspace.test.cjs`
- `web/tests/ux2-opportunities.test.cjs`
- `data/reports/ux2/screenshots/*.png`
- `data/reports/ux2/validation_results.md`

No backend, pipeline, trading-rule, threshold, or execution file changed during UX Phase 2.

## Screenshots

- `opportunities-desktop.png`
- `opportunities-laptop.png`
- `opportunities-tablet.png`
- `opportunities-mobile.png`
- `opportunities-canonical-unavailable.png`
- `opportunities-why-expanded.png`

All screenshots are under `data/reports/ux2/screenshots/`.

## Validation Results

- Preflight: 13 passed.
- Frontend unit: 89 passed, 0 failed, 0 skipped.
- UX2 Playwright/browser: 7 passed, 0 failed.
- UX1 compatibility: 5 passed, 0 failed.
- Track 2F compatibility: 8 passed, 0 failed.
- Route-context compatibility: 6 passed, 0 failed.
- Focused canonical backend/API: 33 passed, 0 failed, 2 deprecation warnings.
- Backend regression: 18 passed, 0 failed, 2 deprecation warnings.
- Production build: PASS, 2,204 modules transformed; one non-blocking chunk-size warning.
- Live read-only smoke: one movers request, 24 labeled legacy rows, canonical unavailable shown, zero page errors.
- Diff whitespace check: PASS; Git emitted line-ending notices only.

## Checker Results

- Architecture Checker: PASS.
- Quant/Data Semantics Checker: PASS after repair cycle 1.
- QA Gatekeeper: PASS.
- UI/Performance Checker: PASS.

Repair cycle 1 made trigger confirmation fail closed and preserved rendered Trade fixture timeframe/evaluation identity. No business logic or engine behavior changed.

## UI And Performance Findings

- No horizontal overflow at 1600px, 1366px, 768px, or 390px.
- Mobile priority is symbol, state, direction, trigger/risk, portfolio risk, and freshness.
- One movers request occurs on load; horizon/filter interactions do not duplicate acquisition.
- Rapid horizon changes leave only the final context visible.
- Browser console errors: 0. Page errors: 0.
- Desktop render baseline p50/p95: 627/787 ms.
- Mobile render baseline p50/p95: 664/905 ms.
- Horizon switching p50/p95: desktop 267/392 ms; mobile 286/566 ms.

## Unresolved Dependencies

- A server-owned canonical opportunity-list endpoint does not yet exist.
- A canonical evaluation retrieval-by-ID contract does not yet exist; navigation preserves the ID, while live Trade evaluation remains timestamp/provider driven.
- Market Driver has no approved backend contract and remains `UNAVAILABLE`.
- Durable watchlist persistence is not approved and was not added.
- Phase 11 remains unapproved and no execution controls were added.

## Stop Condition

UX Phase 2 is complete and passes all checker gates. No subsequent UX phase or Phase 11 work has started.
