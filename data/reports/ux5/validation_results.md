# QX UX5 Research Consolidation Validation

## Result

UX5 consolidates research-oriented surfaces into one read-only Research workspace without changing canonical lifecycle, portfolio-risk, trading-rule, or execution behavior.

## Component structure

- `QXResearchWorkspace` owns the Research shell, mode navigation, symbol context, and bounded handoffs.
- `qx-research-model` preserves source values and separates unavailable, source-backed, and historical research views.
- `qx-research-client` uses same-origin read endpoints for market snapshots and historical backtests.
- Existing `Holdings`, `ReferenceRanking`, `MoversWorkspace`, `RSLine`, `QXOptionsIdeas`, and `QXStrategyWorkspaces` are lazy-loaded only by the modes that need them.
- Route-level lazy loading keeps Research and retained legacy analytical components out of the initial application bundle.

## Mode ownership

1. Symbol: source-backed market and structure context; no lifecycle decision.
2. ETF / Sector: ETF relative-strength history and fund constituents; not broker Portfolio.
3. Relative Strength / Rotation: cached sector ranking, rotation, and market movers.
4. Options / Strategy: modeled and legacy-labeled exploration; not canonical Phase 9.
5. Historical / Backtest: historical and simulated research-only outputs.
6. Long-Term Thesis: source-backed context plus user-entered, session-only notes; no recommendation or persistence.

## Legacy aliases

- `ticker_history` -> Symbol
- `relative_strength`, `sector_rotation` -> Relative Strength / Rotation
- `options_ideas`, `options_flow`, `strategy_lab` -> Options / Strategy
- `liquidity_map`, `backtest`, `spx_nq_futures` -> Historical / Backtest

Legacy routes remain available and visibly identify themselves as compatibility views. No legacy route or module was deleted.

## Data semantics

- Cached market snapshots report `SOURCE_BACKED`; missing bars report `UNAVAILABLE` with null price and structure fields.
- Missing rotation inputs are excluded from quadrant classification rather than converted to zero or a default age.
- Missing modeled options values render `UNAVAILABLE`; no contract, score, IV, RV, credit, or probability is fabricated.
- Significant blocks identify `SOURCE-BACKED`, `MODELED`, `STATIC`, `USER-ENTERED`, `LEGACY`, `HISTORICAL`, `SIMULATED`, or `UNAVAILABLE` status as applicable.
- Research never emits WATCH, ARMED, TRIGGERED, TRADEABLE, Phase 9 suitability, or Phase 10 approval.

## Handoffs

- Research -> Trade sends symbol plus explicit horizon/timeframe preferences and clears evaluation identity, timestamp, snapshots, ETF context, account context, and Research mode. Trade performs a fresh canonical evaluation.
- Research -> Portfolio navigates to the canonical read-only Portfolio workspace and does not calculate account risk inside Research.
- ETF Holdings is relabeled and presented as ETF Constituents / Fund weights, never broker Portfolio positions.

## Screenshots

- `data/reports/ux5/screenshots/research-desktop.png`
- `data/reports/ux5/screenshots/research-laptop.png`
- `data/reports/ux5/screenshots/research-mobile.png`
- `data/reports/ux5/screenshots/research-symbol.png`
- `data/reports/ux5/screenshots/research-etf_sector.png`
- `data/reports/ux5/screenshots/research-relative_strength.png`
- `data/reports/ux5/screenshots/research-options_strategy.png`
- `data/reports/ux5/screenshots/research-historical.png`
- `data/reports/ux5/screenshots/research-long_term.png`

## Validation

- Frontend unit: 113 passed, 0 failed.
- UX5 Playwright: 12 passed, 0 failed.
- UX4 compatibility: 7 passed, 0 failed.
- UX3 compatibility: 9 passed, 0 failed.
- UX2 compatibility: 9 passed, 0 failed.
- UX1 compatibility: 5 passed, 0 failed.
- Backend unit: 2,269 passed, 2 skipped, 0 failed.
- Backend integration: 5 passed, 0 failed.
- Backend regression: 18 passed, 0 failed.
- Focused Research/API regression: 13 passed, 0 failed.
- Automated preflight: PASS, all checks.
- Production build: PASS, 2,216 modules transformed; initial JS bundle 225.93 kB and Research lazy chunk 17.58 kB.

## Checker gates

- Architecture: PASS on final repair cycle 3.
- Quant / Data Semantics: PASS on final repair cycle 3.
- QA: PASS on final repair cycle 3.
- UI / Performance: PASS on final repair cycle 3.

## Files changed for UX5

- `ux5_implementation_plan.md`
- `src/qx/interfaces/web.py`
- `tests/unit/test_ux5_research_api.py`
- `tests/regression/test_preflight_data_and_routes.py`
- `web/package.json`
- `web/src/Holdings.jsx`
- `web/src/QXOptionsIdeas.jsx`
- `web/src/QXResearchStudio.jsx`
- `web/src/QXResearchWorkspace.jsx`
- `web/src/QXStrategyWorkspaces.jsx`
- `web/src/RSLine.jsx`
- `web/src/ReferenceRanking.jsx`
- `web/src/dashboard.css`
- `web/src/main.jsx`
- `web/src/qx-research-client.js`
- `web/src/qx-research-client.test.js`
- `web/src/qx-research-fixtures.js`
- `web/src/qx-research-model.js`
- `web/src/qx-research-model.test.js`
- `web/src/qx-v2-feature.js`
- `web/src/qx-v2-feature.test.js`
- `web/src/workspace-context.js`
- `web/src/workspace-context.test.js`
- `web/src/workspace-routes.js`
- `web/tests/ux1-trade-workspace.test.cjs`
- `web/tests/ux5-research.test.cjs`
- `data/reports/ux5/validation_results.md`
- Nine screenshots under `data/reports/ux5/screenshots/`

## Unresolved dependencies

- Fundamental and valuation research remains unavailable until a source-backed contract exists.
- Canonical option-chain suitability remains owned by Trade/Phase 9; Research exposes only clearly modeled or legacy exploration.
- Long-term notes remain session-only because Journal persistence is outside UX5 scope.
- Retained legacy provider services may contain older fallback behavior, but they are not imported or called by the consolidated UX5 snapshot path.

UX6, Market Driver work, Journal persistence, Phase 11, broker writes, and execution controls were not started.
