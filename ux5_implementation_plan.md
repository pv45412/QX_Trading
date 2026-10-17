# QX UX5 Research Consolidation Implementation Plan

## Technical Goal

Create one responsive Research destination that owns analytical depth without publishing or inferring canonical lifecycle, options-suitability, or portfolio-risk decisions. Preserve the approved Today → Opportunities → Trade → Portfolio baseline and retain legacy routes as compatibility aliases.

## Research Modes

1. **Symbol** — source-backed cached market snapshot, structure history summary, provenance, and fresh Trade/Portfolio handoffs.
2. **ETF / Sector** — ETF relative-strength history and constituent holdings, explicitly separated from broker Portfolio.
3. **Relative Strength / Rotation** — cached sector rankings and movers with source/freshness labels.
4. **Options / Strategy Research** — modeled options ideas and hypothetical payoff tools; never canonical Phase 9 output.
5. **Historical / Backtest** — user-triggered historical simulation with explicit HISTORICAL / SIMULATED / RESEARCH_ONLY labeling.
6. **Long-Term Thesis** — user-entered, non-persisted thesis notes plus source-backed context; no recommendation or journal persistence.

## Component And File Boundaries

- Add `web/src/QXResearchWorkspace.jsx` as the presentation-only Research owner.
- Add thin research client/model modules and unit tests.
- Lazy-load Research and its heavier legacy analytical components from `web/src/main.jsx`.
- Extend workspace context with validated `research_mode` only.
- Map legacy research/market routes to a deterministic Research mode without deleting routes.
- Reuse `Holdings`, `RSLine`, `ReferenceRanking`, `MoversWorkspace`, `QXOptionsIdeas`, and `QXStrategyWorkspaces` only in their appropriate modes.
- Replace hard-coded strategy API origins with same-origin relative paths.
- Make `/api/market/{symbol}/snapshot` truthful when source bars are unavailable; do not fabricate market values or structure.

## Data Contracts

- Market snapshot preserves `symbol`, `status`, `last_price`, `data_as_of`, `retrieved_at`, `structure`, `source`, `source_class`, and reason code.
- Research adapters preserve null values and never map modeled/static/legacy output into canonical state.
- Backtest results remain historical simulation metrics and never become live confidence or lifecycle fields.
- Trade handoff sends only validated symbol plus explicitly selected horizon/timeframe and clears evaluation identity.
- Portfolio handoff navigates to the read-only Portfolio owner and performs no portfolio calculation in Research.

## Provenance And Labels

Every major panel is labeled as one of `CANONICAL`, `SOURCE-BACKED`, `MODELED`, `STATIC`, `USER-ENTERED`, or `LEGACY`. Historical outputs additionally display `HISTORICAL`, `SIMULATED`, and `RESEARCH_ONLY`. Canonical labels are reserved for links to Trade/Portfolio ownership; Research does not publish canonical decisions.

## Compatibility And Performance

- Existing legacy route URLs continue to resolve and display a visible compatibility label.
- Only the active Research mode mounts its data-owning components.
- Research and heavier subcomponents are lazy-loaded.
- Mode changes must not issue requests for inactive modes.
- No new backend engine, cache, queue, provider, or execution surface is introduced.

## Validation

- Add frontend model/context tests and UX5 Playwright coverage for all six modes, legacy labeling, holdings separation, handoffs, request isolation, and four viewports.
- Run relevant API tests, frontend tests, production build, UX1–UX4 compatibility, backend regression, and preflight.
- Run independent Architecture, Quant/Data Semantics, QA, and UI/Performance checker gates before completion.

## Non-Goals

- Market Driver engine
- Journal persistence
- Phase 11 or broker writes
- Execution controls
- Trading-rule or threshold changes
- Destructive legacy removal

