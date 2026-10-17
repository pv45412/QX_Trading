# Component Reuse Map

## Classification Definitions

- **REUSE:** retain component responsibility with limited composition/styling changes.
- **REFACTOR:** preserve useful behavior but split, rename, or bind to a clearer contract.
- **MERGE:** absorb useful presentation into a target destination; stop presenting the
  component as an independent workflow.
- **LEGACY_ONLY:** isolate for comparison/compatibility; never present as canonical.
- **REPLACE_LATER:** retain temporarily until a reviewed canonical replacement exists.

## Core Components

| Component | Classification | Target owner | Required treatment |
|---|---|---|---|
| `QXLifecyclePanel` | REUSE | Trade | Preserve canonical state/evidence semantics; optionally split summary, rail, stages, and WHY into reusable presentation children. |
| `QXDayTraderTerminal` | MERGE | Today / Trade | Reuse selected market/level layouts; remove or clearly isolate competing legacy signal state. |
| `QXInstitutionalScanner` | REFACTOR | Opportunities | Reuse filters/table interactions; replace client-derived canonical claims with server-owned opportunity records. |
| `QXOptionsScanner` | LEGACY_ONLY | Opportunities legacy comparison / Research | Keep isolated until canonical options expression covers its approved use; never label as canonical. |
| `QXOptionsIdeas` | REFACTOR | Research | Keep exploratory modeling with explicit modeled provenance; Trade consumes only canonical options expression. |
| `QXResearchStudio` | REFACTOR | Research | Split supported research from static/generated narrative and label provenance. |
| `QXPositionAdvisor` | REFACTOR | Portfolio / Research | Reuse position-analysis presentation; stop using it as Idea Tracking or Outcome Journal. |
| `Holdings` | REFACTOR | Research | Rename to ETF Constituents/Fund Holdings Research; remove any implication of broker portfolio ownership. |
| `QXSystemControl` | REFACTOR | System | Split real provider operations from prototype cache/jobs; add true run/rules views only when backed. |
| `QXBentoDashboardLayout` | REUSE | Global shell | Retain responsive shell/error isolation; simplify to one global navigation and verified header telemetry. |
| `WorkspaceNavigation` | REFACTOR | Global shell | Replace duplicate top/side/quick-jump hierarchy with target primary nav and destination modes. |

## Supporting Components

| Component | Classification | Target owner | Required treatment |
|---|---|---|---|
| `QXTradingSuite` | MERGE | Trade / Research | Extract canonical lifecycle placement; move unrelated GEX/VWAP/ORB/investor panels to owning contexts. |
| `ReferenceRanking` | REUSE | Research / Opportunities | Reuse ranking/table modes with clear data freshness and horizon context. |
| `MoversWorkspace` | REFACTOR | Opportunities / Today | Reuse market-movement summaries; do not equate movers with canonical setups. |
| `MarketMovers` | REUSE | Opportunities / Today | Retain generic table presentation with provenance. |
| `SPXFuturesWorkspace` | REFACTOR | Today / Research / Trade | Split compact market pulse from deeper context; label live/static/simulated sections. |
| `QXDailyNewsPrompt` | REPLACE_LATER | Today / Research | Retain only as clearly labeled context until supported event/driver contracts exist. |
| `QXStrategyWorkspaces` | REUSE | Research | Keep payoff/strategy calculator after endpoint/config cleanup and provenance labeling. |
| `AIReview` | LEGACY_ONLY | Research legacy evidence | Isolate from canonical WHY; no automated invocation or lifecycle influence. |
| `RSLine` | REUSE | Research | Retain focused relative-strength visualization with timestamp/provenance. |
| `LiveRefresh` | REFACTOR | Owning destination | Replace page-global refresh behavior with source-aware, read-only refresh controls. |
| `ErrorBoundary` | REUSE | All | Continue isolating major panels and provide destination-specific recovery. |
| `qx-v2-client` / `useQxV2Evaluation` | REUSE | Trade and compact canonical summaries | Maintain one V2 API path and request/evaluation timestamp semantics. |
| `qx-v2-adapter` | REUSE | Canonical presentation | Keep thin and lossless; no trading inference or evidence normalization. |

## Market and Sector Surfaces

| Current surface | Classification | Target placement |
|---|---|---|
| Relative-strength ranking | REUSE | Research ETF & Sector; compact Today/Opportunity context |
| Market movers | REUSE | Opportunities discovery; short Today summary |
| Sector rotation | MERGE | Research ETF & Sector |
| SPX/futures session context | REFACTOR | Today pulse and Research detail |
| Legacy terminal SMC/VWAP/tape | LEGACY_ONLY then REPLACE_LATER | Supporting comparison only until canonical fields cover the use case |
| Canonical structure/regime/direction | REUSE | Trade primary evidence; compact Today/Opportunities summaries |
| ETF holdings/concentration | REFACTOR | Research ETF Constituents |
| Broker positions/exposure | NEW COMPOSITION from existing canonical data | Portfolio |

## Extraction Boundaries

Recommended reusable presentation primitives for future implementation:

- `LifecycleStateBadge`
- `LifecycleRail`
- `DecisionSummary`
- `TriggerInvalidationCard`
- `StageAvailability`
- `FreshnessProvenance`
- `ReasonCodeList`
- `EvidenceAudit`
- `OpportunityRow` / `OpportunityCard`
- `PortfolioRiskSummary`
- `MarketDriverSummary` (display only)

These primitives must consume backend-owned fields. Extraction should not duplicate
canonical adaptation logic across pages.

## Legacy Isolation Rules

- Legacy components can remain accessible through compatibility routes.
- Legacy state names display a `LEGACY` provenance label.
- Legacy values never fill missing canonical fields.
- Shadow comparison stays out of primary decision summaries.
- Removal requires migration tests, consumer verification, and an approved destructive
  migration; this package authorizes none.
