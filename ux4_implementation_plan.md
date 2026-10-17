# QX UX4 Portfolio Implementation Plan

## Goal

Implement the canonical read-only Portfolio workspace without changing Phase 10 rules,
broker permissions, execution behavior, or the approved Today → Opportunities → Trade
baseline.

## Architecture

- Add `GET /api/v2/qx/portfolio` to the legacy-free v2 router.
- Reuse `CanonicalAccountSnapshotProvider` and `CanonicalSnapshotRepository`; do not use
  the legacy portfolio service or ETF Holdings data.
- Return only internal `qxacct_*` account identifiers and approved read-only balances,
  positions, exposure, provenance, freshness, and data-quality state.
- Preserve point-in-time behavior: explicit evaluation timestamps read only persisted
  snapshots visible at that timestamp; live requests establish evaluation time after
  provider acquisition.
- Use the existing `/api/v2/qx/evaluate/{symbol}` and canonical Phase 10 result for linked
  candidate impact. The frontend does not calculate risk decisions or thresholds.

## Frontend

- Replace the Portfolio placeholder with `QXPortfolioWorkspace`.
- Present account summary, attention, positions, exposure, candidate impact, and data
  quality in the approved responsive hierarchy.
- Add deterministic, explicitly labeled fixture states for review only.
- Add Trade → Portfolio and Portfolio → Trade links that preserve canonical context and
  clear stale evaluation identity when evaluating a different position.
- Keep `Holdings.jsx` exclusively labeled and used as fund/ETF constituent research.

## Safety Boundaries

- No broker write methods or execution controls.
- No raw account numbers, credentials, tokens, or secrets in API responses or UI.
- No Phase 10 math or trading-rule changes.
- Missing, stale, partial, sector-unknown, and Greek-unavailable evidence remains explicit.
- No frontend null-to-zero coercion.

## Validation

- Backend API/provider privacy and point-in-time tests.
- Frontend model/client tests and UX4 Playwright states/responsive screenshots.
- UX1, UX2, UX3, Track2F, frontend suite, production build, preflight, and applicable
  backend unit tests.
- Independent Architecture, Quant/Data Semantics, QA, and UI/Performance checker gates.
