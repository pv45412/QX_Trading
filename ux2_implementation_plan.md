# QX UX Phase 2 Implementation Plan

## Technical Goal

Implement the approved Opportunities discovery and triage destination for `DAY`, `SWING`, and `INVEST` while preserving Trade Workspace as the sole owner of the complete canonical lifecycle.

## Data Contracts

- Canonical opportunity rows project existing `core_v1` evaluation fields without rescoring or reinterpretation.
- The repository currently has no server-owned canonical opportunity-list endpoint. Live UI must report that dependency as unavailable.
- Existing `/api/movers/{universe}` data may appear only in a separate `LEGACY SOURCE` section with no canonical state, trigger, or tradeability fields.
- Deterministic canonical fixtures are available only behind an explicit runtime test flag.

## Component Boundaries

- `QXOpportunitiesWorkspace`: controls, empty/partial states, canonical list, legacy list, and Trade handoff.
- `qx-opportunities-model`: pure canonical projection, direct-field filtering/sorting, and legacy payload validation.
- `qx-opportunities-client`: read-only verified legacy discovery acquisition.
- `qx-opportunities-fixtures`: deterministic canonical test records built from approved V2 fixtures.
- `main.jsx`: target Opportunities route ownership; legacy scanner routes remain unchanged.

## Risks And Edge Cases

- No canonical opportunity feed: fail visibly with `CANONICAL DATA UNAVAILABLE`; never manufacture candidates.
- Legacy data leakage: label every legacy row and omit canonical badges/fields.
- Handoff drift: preserve symbol, horizon, timeframe, evaluation timestamp, and evaluation identity when supplied.
- Stale browser results: abort discovery requests on unmount and prevent stale responses from replacing current state.
- Partial downstream stages: preserve `UNAVAILABLE` values and valid upstream evidence.

## Verification

- Frontend unit and production build.
- Opportunities Playwright tests across desktop, laptop, tablet, and mobile.
- Canonical fixture-state and Trade handoff tests.
- Legacy route compatibility and relevant V2/API tests.
- Independent Architecture, Quant/Data Semantics, QA, and UI/Performance gates.
