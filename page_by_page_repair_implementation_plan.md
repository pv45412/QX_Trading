# QX Page-by-Page Repair Implementation Plan

## Technical Goal and Requirements

Restore the approved contracts for the six primary product workspaces without changing
canonical trading semantics, provider behavior, backend API schemas, broker permissions,
or execution controls.

The repair must:

- keep `Today -> Opportunities -> Trade -> Portfolio -> Research` as the product flow;
- preserve all canonical evaluation identity fields during cross-workspace handoff;
- keep unavailable, blocked, partial, and stale states distinct and fail-closed;
- retain the current responsive Trade hero instead of restoring its superseded layout;
- reconcile browser tests with the current Trade hero using stable selectors;
- restore approved Today hierarchy, action labels, and unavailable-state wording;
- preserve read-only operation and keep Phase 11 disabled;
- introduce no synthetic market, portfolio, options, or execution data.

## Baseline Evidence

- Automated preflight: 13/13 checks passed.
- Live desktop/mobile audit: all six pages loaded with zero page errors, console errors,
  failed API responses, or horizontal overflow.
- Frontend unit suite: 130 passed, 3 failed.
- UX1 Trade browser suite: 1 passed, 5 failed; all five failures use the obsolete
  `.qx-decision-title .qx-state` selector after lifecycle state moved to the Trade hero.
- UX2 Opportunities browser suite: 9 passed, 2 failed; both handoffs reach Trade with the
  correct URL and visible state but wait on the obsolete Trade selector.
- UX3 Today browser suite: 3 passed, 7 failed; failures cover approved section/action copy,
  compact unavailable-driver presentation, one empty-state sentence, and the obsolete
  Trade selector.
- UX4 Portfolio browser suite: 5 passed, 2 failed; failures cover the Trade portfolio-link
  label and the approved Today positions heading.
- UX5 Research browser suite: 12/12 passed.
- UX6 System browser suite: 5/5 passed.

## Page Findings and Repair Scope

### Today

Files:

- `web/src/QXTodayWorkspace.jsx`
- `web/src/QXMarketDriverPanel.jsx`
- `web/src/dashboard.css` only if compact unavailable-state styling needs adjustment
- `web/src/qx-today-model.test.js`
- `web/tests/ux3-today.test.cjs`

Repairs:

- Restore approved headings: `Market Drivers`, `Positions Requiring Attention`, and
  `Material Events / Data Health`.
- Restore `View all opportunities` as the explicit Opportunities action.
- Restore the approved live empty-state sentence using `LIVE observations require attention`.
- Render one compact, truthful Market Driver unavailable state with no inference claim.
- Use title-case provenance labels required by the Today source contract.
- Update the Trade handoff assertion to target the current Trade hero state.

### Opportunities

Files:

- `web/tests/ux2-opportunities.test.cjs`

Repairs:

- Keep the current handoff URL behavior because direct reproduction confirms symbol,
  horizon, timeframe, evaluation timestamp, evaluation ID, ETF context, and fixture state
  are preserved.
- Replace the obsolete Trade state locator with the current hero state locator.

### Trade

Files:

- `web/src/QXTradeWorkspace.jsx`
- `web/src/qx-trade-workspace-model.js`
- `web/src/qx-trade-workspace-model.test.js`
- `web/tests/ux1-trade-workspace.test.cjs`

Repairs:

- Preserve the current above-the-fold Trade hero and use `.qx-trade-hero-state` as the
  browser contract for canonical lifecycle state.
- Restore the explicit `View Portfolio Impact` action label.
- Align ARMED next-action wording with the approved direct instruction.
- Keep a missing backend Market Driver explicitly unavailable without implying a
  sub-threshold determination.
- Preserve one-request evaluation behavior and all existing lifecycle semantics.

### Portfolio

Files:

- `web/tests/ux4-portfolio.test.cjs`

Repairs:

- Revalidate Trade-to-Portfolio identity after restoring the action label.
- Revalidate Today-to-Portfolio routing after restoring the approved Today heading.
- Do not change portfolio calculations, account data, or risk semantics.

### Research

No source repair is planned. Retain the current implementation and rerun its complete
browser suite as a regression guard.

### System

No source repair is planned. Retain the current implementation and rerun its complete
browser suite as a regression guard. Live `DEGRADED` status caused only by unavailable
process-memory verification remains a truthful operational state, not a UI failure.

## Data and API Contracts

No backend schema or route changes are planned.

- `POST /api/v2/qx/evaluate/{symbol}` remains the canonical Trade evaluation route.
- `GET /api/v2/qx/opportunities` remains the canonical read-only opportunity list.
- `GET /api/v2/qx/portfolio` remains read-only and may truthfully return `PARTIAL`.
- `GET /api/system/overview` remains the System status source.
- Existing URL context keys and canonical evaluation identity remain unchanged.

## Risk Drivers and Edge Cases

- Do not convert after-hours `BLOCKED` evaluations into available states.
- Do not treat empty opportunity lists as service failures.
- Do not convert partial brokerage evidence into approval or execution readiness.
- Do not reintroduce the old Trade decision-summary state placement solely to satisfy a
  stale selector.
- Do not clear or overwrite unrelated staged, unstaged, or untracked user work.
- Keep fixture-only query parameters out of production workspace context contracts.
- Preserve mobile ordering, collapsed evidence, and zero horizontal overflow.

## Implementation Sequence

1. Repair Trade copy, action label, and stable browser selectors.
2. Repair Opportunities-to-Trade handoff assertions.
3. Restore Today hierarchy, actions, provenance labels, and empty states.
4. Repair Today-to-Trade and Today-to-Portfolio assertions.
5. Revalidate Portfolio cross-workspace identity behavior.
6. Run all frontend unit and UX browser suites.
7. Run production build, backend regression, and preflight.
8. Capture first/final desktop and mobile evidence under a dedicated page-repair report.

## Verification and Acceptance

- `npm test` passes with no failures.
- UX1 through UX6 browser suites all pass independently and together.
- `npm run build` passes.
- `pytest tests/regression/` passes.
- `python -m qx.tools.run_preflight_checks` reports 13/13 passes.
- Live Today, Opportunities, Trade, Portfolio, Research, and System pages have zero page
  errors, console errors, failed API responses, and horizontal overflow at desktop and
  mobile widths.
- Final evidence records expected fail-closed live states separately from code defects.

## Breaking Changes and Human Gates

No breaking API, trading-rule, threshold, persistence, provider, credential, broker-write,
or execution change is proposed. Source implementation starts only after explicit user
approval of this plan, as required by the QX design-first protocol.
