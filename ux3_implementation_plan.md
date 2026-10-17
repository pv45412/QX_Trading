# QX UX Phase 3 Implementation Plan

## Technical Goal

Implement Today as a sparse market-attention and routing surface using verified canonical context without creating another scanner, opportunity engine, lifecycle engine, portfolio model, or system dashboard.

## Data Contracts

- Market Pulse requests one canonical `core_v1` evaluation each for SPY and QQQ through the existing V2 client. SPX remains unavailable until a verified canonical contract exists.
- Active QX Opportunities reuses the Phase 2 canonical opportunity projection. Live opportunities remain unavailable until a server-owned list endpoint exists.
- Positions remain unavailable without an approved canonical read endpoint. Fixture-only partial evidence validates presentation semantics.
- Material health combines direct canonical publication failures and non-healthy `/api/ops/health` states. Healthy operational detail is omitted.
- Verified movers may appear only as secondary `LEGACY SOURCE` context.

## Component Boundaries

- `QXTodayWorkspace`: ordered page composition and navigation actions.
- `useTodayAttentionData`: abortable acquisition of two canonical pulse evaluations, material health, and legacy context.
- `qx-today-model`: direct-field pulse projection, presentation-only opportunity ordering, and material-exception filtering.
- `qx-today-fixtures`: deterministic review states behind an explicit runtime flag.
- `main.jsx`: preferred Today route ownership while legacy Today routes remain unchanged.

## Risks And Edge Cases

- Missing canonical opportunity feed: publish `CANONICAL OPPORTUNITIES UNAVAILABLE`.
- Missing position endpoint: publish `UNAVAILABLE`; never substitute ETF holdings.
- Market Driver absence: always publish `UNAVAILABLE`.
- Partial or blocked canonical pulse: preserve status, reason, and evaluation timestamp.
- Context handoff: preserve symbol, horizon, timeframe, evaluation timestamp, and identity.
- Stale requests: abort prior acquisitions and ignore late results.

## Verification

- Frontend unit and production build.
- UX3 Playwright fixtures and routing.
- UX2, UX1, and Track 2F compatibility.
- Focused V2/API tests, regression, and preflight.
- Independent Architecture, Quant/Data Semantics, QA, and UI/Performance gates.
