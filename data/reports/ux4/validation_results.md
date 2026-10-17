# QX UX4 Portfolio Validation Results

## Result

UX4 Portfolio: **PASS**

The implementation provides a read-only canonical Portfolio workspace backed by the existing Schwab account snapshot provider and canonical snapshot repository. It does not add broker writes, execution controls, Phase 11 behavior, trading-rule changes, or Holdings reuse.

## UX4 Files Changed

- `ux4_implementation_plan.md`
- `src/qx/brokers/schwab/accounts.py`
- `src/qx/interfaces/qx_v2.py`
- `src/qx/portfolio/models.py`
- `src/qx/portfolio/workspace.py`
- `tests/unit/test_phase10_portfolio_risk.py`
- `tests/unit/test_track2_providers.py`
- `tests/unit/test_ux4_portfolio_api.py`
- `web/package.json`
- `web/src/dashboard.css`
- `web/src/main.jsx`
- `web/src/QXPortfolioWorkspace.jsx`
- `web/src/QXTradeWorkspace.jsx`
- `web/src/qx-portfolio-client.js`
- `web/src/qx-portfolio-client.test.js`
- `web/src/qx-portfolio-fixtures.js`
- `web/src/qx-portfolio-model.js`
- `web/src/qx-portfolio-model.test.js`
- `web/src/qx-v2-feature.js`
- `web/src/qx-v2-feature.test.js`
- `web/src/useQxPortfolio.js`
- `web/src/workspace-context.js`
- `web/src/workspace-context.test.js`
- `web/tests/ux1-trade-workspace.test.cjs`
- `web/tests/ux4-portfolio.test.cjs`
- `data/reports/ux4/validation_results.md`
- Eight PNG review artifacts under `data/reports/ux4/screenshots/`

## Component Structure

1. Account / Portfolio Summary
2. Canonical Positions
3. Risk & Exposure
4. Positions Requiring Attention
5. Trade / Opportunity Impact
6. Data Quality / Partial Evidence

Desktop, laptop, tablet, and mobile layouts preserve this hierarchy. Mobile moves attention ahead of the full positions list while retaining position evidence behind details disclosure.

## Canonical Data Flow

- `GET /api/v2/qx/portfolio` acquires one live read-only account snapshot or reads one point-in-time snapshot for an explicit evaluation timestamp.
- Historical requests never invoke the live account provider.
- `data_as_of` and `retrieved_at` visibility are enforced by the canonical snapshot repository and v2 route.
- Missing P/L and open-order values remain `null`; the account context is automatically marked `PARTIAL` so existing Phase 10 fail-closed behavior blocks before risk arithmetic.
- Account identifiers are transformed to internal `qxacct_*` values. Raw broker account identifiers and credentials are not returned.
- Canonical `qxacct_*` identifiers survive validated workspace routing; raw numeric account identifiers remain rejected.

## Phase 10 Projection

- The frontend displays existing canonical `portfolio_risk` output without recalculation.
- Linked impact evaluation requires both a symbol and an explicit evaluation timestamp.
- Portfolio and evaluation endpoints use the same point-in-time repository selection at that timestamp; neither reacquires a live account snapshot.
- No Phase 10 engine, threshold, approval, lifecycle, or trading-rule behavior was changed for UX4.

## Routing And Separation

- Trade to Portfolio preserves symbol, horizon, timeframe, evaluation timestamp, and evaluation identity without injecting ETF context.
- Portfolio position to Trade starts a fresh evaluation and clears stale evaluation identity.
- Today to Portfolio preserves horizon/timeframe without leaking symbol context.
- Portfolio uses canonical broker positions only. Holdings remains ETF constituent research.
- Portfolio is lazy-loaded and an ordinary Portfolio visit performs one account request with no implicit candidate evaluation.

## Required States

Validated fixture-only review states are clearly labeled and include healthy, partial, stale, unknown sector, unavailable Greeks, Phase 10 approved, Phase 10 vetoed, and no account.

## Checker Gates

- Architecture Checker: **PASS** after routing and point-in-time linkage re-review.
- Quant/Data Semantics Checker: **PASS** after null preservation and model-level partial-state repair.
- QA Gatekeeper: **PASS**, 97 focused Python plus 105 frontend unit tests.
- UI/Performance Checker: **PASS**, with no new request or render regression.

## Automated Validation

- Focused provider, Phase 10, and Portfolio API: **97 passed**.
- Full backend unit suite: **2268 passed, 2 skipped, 0 failed**.
- Backend regression suite: **18 passed, 0 failed**.
- Frontend unit suite: **105 passed, 0 failed**.
- UX4 Playwright: **7 passed, 0 failed**.
- Locked UX3 Playwright: **9 passed, 0 failed**.
- Locked UX2 Playwright: **9 passed, 0 failed**.
- Locked UX1 Playwright: **5 passed, 0 failed**.
- Track 2F Playwright: **8 passed, 0 failed**.
- Production build: **PASS**, 2213 modules transformed.
- Build observation: the existing main bundle remains above Vite's advisory 500 kB threshold; Portfolio is isolated in a 21.34 kB lazy chunk. No optimization architecture was introduced.

## Screenshots

- `portfolio-desktop.png`
- `portfolio-laptop.png`
- `portfolio-tablet.png`
- `portfolio-mobile.png`
- `portfolio-partial.png`
- `portfolio-stale.png`
- `portfolio-vetoed.png`
- `portfolio-no-account.png`

## Known Data Dependencies

- Broker-supplied P/L remains unavailable when Schwab omits it; QX does not calculate a replacement.
- Option-position Greeks remain unavailable/partial unless supplied by canonical evidence; QX does not fabricate them.
- Linked Phase 10 impact requires an explicit timestamped Trade evaluation and available historical bars/options/account evidence.
- No broker writes, execution controls, Phase 11 work, Research consolidation, Journal persistence, or Market Driver work are included.
