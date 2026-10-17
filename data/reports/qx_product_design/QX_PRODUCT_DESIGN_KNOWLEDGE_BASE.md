# QX Product Design Knowledge Base

## Status and Scope

This package is the design-only target for QX information architecture and UX
consolidation. It is grounded in the verified current-state UI review dated 2026-09-16:
22 routed labels, seven render families, duplicate navigation, and three broken
end-to-end journeys. No UI code, route behavior, trading rule, Phase 3-10 engine, broker
permission, or Phase 11 execution behavior is changed here.

## Product Thesis

**Complex engine, simple workflow.** QX should expose the minimum information needed
for the next user decision while retaining complete evidence, provenance, and audit in
secondary views.

The product is one connected workflow across three horizons:

```text
DAY / SWING / INVEST
        |
Today -> Opportunities -> Trade Workspace
   |            |              |
   |            |              +-> canonical lifecycle / options / portfolio risk
   |            +-> discovery and triage
   +-> attention and routing

Portfolio <-> Trade Workspace <-> Research
System supports every destination with provider/data health.
Journal remains secondary until it has durable records.
```

## Target Primary Navigation

```text
Today | Opportunities | Trade | Portfolio | Research | System
```

Optional secondary destination: `Journal`.

This replaces competing top navigation, left-sidebar navigation, and Markets-page
quick jumps with one global hierarchy. Existing routes remain as compatibility aliases
during migration.

## Page Ownership Summary

| Destination | Owns | Does not own |
|---|---|---|
| Today | Material market, opportunity, position, and health attention | Full scanner, deep evidence, credentials, orders |
| Opportunities | Horizon-filtered discovery and triage | Final trade decision or client-derived canonical state |
| Trade | One full `core_v1` decision lifecycle | Discovery lists, deep research, execution |
| Portfolio | Real read-only broker accounts, positions, exposure, constraints | ETF constituent research or broker writes |
| Research | Symbol/ETF/sector/history/strategy/backtest depth | Canonical lifecycle publication or portfolio approval |
| System | Providers, data, jobs, runs, rules metadata | Trading decisions |
| Journal | Future durable ideas/trades/outcomes | Current Position Advisor relabeled as persistence |

Detailed ownership and all 22 route classifications are in `page_ownership.md` and
`navigation_target.md`.

## Canonical Lifecycle Placement

The approved `QXLifecyclePanel` remains the foundation:

```text
WATCH -> ARMED -> TRIGGERED -> TRADEABLE -> OPTIONS_SUITABLE -> PORTFOLIO_APPROVED
```

Valid terminal/alternate states remain:

`NO_SETUP`, `BLOCKED`, `NOT_TRADEABLE`, `OPTIONS_NOT_SUITABLE`,
`PORTFOLIO_VETOED`, and `EXPIRED`.

Trade Workspace owns the complete lifecycle. Today and Opportunities display compact
canonical summaries that link to it. Portfolio displays the relevant risk result.
Research may link to a current evaluation but does not calculate a lifecycle.

Legacy terminal/scanner state labels must converge toward this language or remain
isolated with a visible `LEGACY` label. They cannot fill missing canonical values.

## Trade Workspace Decision Hierarchy

The top of Trade Workspace answers:

1. What is happening?
2. What does QX see?
3. What are we waiting for?
4. Where is QX wrong?
5. Is there a trade?

The page order is:

1. Decision Summary
2. Market Driver
3. Lifecycle
4. Structure / Regime / Direction
5. Trigger / Invalidation / Targets
6. Participation / Tradeability
7. Options Expression
8. Portfolio Risk
9. WHY / Evidence
10. Future Execution Readiness

Primary views show decision, state, trigger, risk, and next action. Raw rule IDs,
weights, timestamps, and stage details remain in expandable WHY/Audit. The full
specification is in `trade_workspace_spec.md`.

## Market Driver

Market Driver is a future backend-owned deterministic presentation input. The UI may
show primary/secondary drivers, strength, persistence, confirming/conflicting evidence,
coverage, timestamps, and provenance. The frontend must not infer a driver from regime,
news, direction, or market color. Until the backend contract exists, the correct display
is `UNAVAILABLE`. See `market_driver_spec.md`.

## Opportunities

One Opportunities surface supports `DAY`, `SWING`, and `INVEST`. A row prioritizes:
symbol, canonical state, direction, playbook/thesis, market driver, trigger,
invalidation, tradeability, risk status, coverage, and freshness. Selecting a canonical
row opens Trade Workspace with the same evaluation context. Low or zero setup counts are
valid observations; the UI never manufactures fallback candidates. See
`opportunities_spec.md`.

## Today

Today is an attention surface, not another scanner. Its order is Market Pulse, Market
Drivers, Active QX Opportunities, Positions Requiring Attention, and material Events /
Data Health. Healthy operational detail remains in System. See `today_spec.md`.

## Portfolio Distinction

Portfolio means actual read-only brokerage accounts and positions. The current
`Holdings` component means ETF constituents and moves to Research under an explicit
fund-research label. Unknown sector provenance leaves concentration evidence partial
and cannot silently pass required risk gates. See `portfolio_spec.md`.

## Research Ownership

Research contains instrument, ETF/sector, options/strategy, historical, backtest, and
long-term thesis complexity. It distinguishes canonical, source-backed, modeled,
static, user-entered, and legacy information. Exploratory options models stay here;
canonical options suitability stays in Trade. See `research_spec.md`.

## Signal-to-Execution Boundary

`PORTFOLIO_APPROVED` is not an order and does not imply readiness. A future separately
approved `EXECUTION_READY` assessment would require fresh data, valid trigger,
tradeability, option suitability when applicable, portfolio approval, quantity cap,
spread/slippage checks, duplicate prevention, session eligibility, kill switches, and
authorization. No such behavior is implemented. See `execution_handoff_spec.md`.

## Component Strategy

High-value reuse centers on `QXLifecyclePanel`, the V2 client/adapter, the global shell,
error boundaries, rankings, charts, and strategy payoff views. Monolithic terminal,
scanner, system, research, and suite components should be decomposed by page ownership.
Legacy AI/options/scanner decisions remain isolated until canonical replacements exist.
See `component_reuse_map.md`.

## Consolidation Decisions

1. Replace 22 primary labels with six destinations and one optional secondary Journal.
2. Make Trade Workspace the sole owner of the complete canonical decision chain.
3. Treat horizon as context/filter, not a separate application.
4. Merge Scanner/Broad Watchlist/Heatmap into Opportunities modes.
5. Merge Command Center/Morning Report/Daily Workflow into Today modes.
6. Move ETF holdings, sector rotation, relative strength, and modeled strategies into
   Research.
7. Create a true broker Portfolio from the canonical account snapshot; do not reuse the
   ETF Holdings label.
8. Convert quick jumps into commands/deep links after destination routes exist.
9. Keep System operational and separate real provider status from prototypes.
10. Preserve all current routes as aliases until migration tests and rollback paths pass.

## Recommended Implementation Sequence

### 1. Shared contracts and shell

- Approve destination ownership, target routes, and cross-page context.
- Add route aliases without deleting existing routes.
- Consolidate global navigation in the existing shell.
- Extract lossless canonical presentation primitives from `QXLifecyclePanel` only as
  needed; preserve adapter semantics.

### 2. Trade Workspace

- Create the Trade route around the existing V2 client and lifecycle panel.
- Add the five-question summary and ordered canonical sections.
- Keep Market Driver unavailable until a backend contract is separately approved.
- Validate all progressive, terminal, partial, and unavailable states.

### 3. Opportunities

- Create one surface with horizon modes.
- Initially label legacy discovery sources; do not promote client scores to canonical.
- Link canonical results to Trade Workspace.
- Add a server-owned opportunity record only through a separately reviewed backend task.

### 4. Today

- Compose compact, exception-oriented summaries from existing verified sources.
- Link active items to Trade, Portfolio, Research, or System.
- Remove duplicate scanner/research detail from the Today page.

### 5. Portfolio

- Build from the existing canonical read-only account snapshot and Phase 10 result.
- Enforce safe account identifiers and partial provenance semantics.
- Rename/move ETF `Holdings` to Research before exposing Portfolio broadly.

### 6. Research and System consolidation

- Split Research into real modes and visibly label modeled/static/legacy content.
- Split System real operations from placeholders.
- Keep Journal secondary until persistence is designed and approved.

### 7. Compatibility retirement

- Migrate internal links and tests.
- Measure usage and verify rollback.
- Seek human approval before destructive route/component removal.
- Phase 11 remains a separate milestone.

## Required Validation for Future Implementation

- route compatibility and context-preservation tests
- lifecycle state and evidence-loss regression tests
- no canonical/legacy fallback leakage
- partial/unavailable downstream stage tests
- account identifier and credential privacy checks
- desktop/laptop/tablet/mobile visual checks
- browser journeys for day, swing, and long-term users
- full frontend/backend regression appropriate to each implementation task

## Unresolved Product Questions

1. What persistent object and API will back watchlists, ideas, journal records, and
   monitoring transitions?
2. Which backend service will own market-driver determination and history?
3. What is the approved multi-timeframe contract for SWING and INVEST views?
4. Which opportunity API will rank canonical evaluations without duplicating trading
   logic in the frontend?
5. Which account/position fields are approved for display beyond current Phase 10 needs?
6. Should Journal become primary only after execution records exist, or can durable
   research ideas activate it earlier?
7. Which current static/simulated panels should be retired versus connected to real
   data in later milestones?
8. What route telemetry and deprecation window are required before old URLs can be
   removed?

Questions involving new engine logic, thresholds, persistence architecture, broker
writes, or destructive migration require explicit human approval.

## Artifact Index

- `page_ownership.md`
- `user_flows.md`
- `trade_workspace_spec.md`
- `market_driver_spec.md`
- `opportunities_spec.md`
- `today_spec.md`
- `portfolio_spec.md`
- `research_spec.md`
- `navigation_target.md`
- `execution_handoff_spec.md`
- `component_reuse_map.md`
- `wireframes.md`

## Stop Boundary

This knowledge base ends the design milestone. Do not implement the UI, alter trading
rules, begin Phase 11, or delete legacy routes/components without a new approved task.
