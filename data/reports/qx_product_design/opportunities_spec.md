# Opportunities Specification

## Purpose

Opportunities is the unified discovery and triage surface. It replaces the current
experience of entering duplicate Scanner, Broad Watchlist, Heatmap, and composite
Markets sections. Scanner logic discovers; Trade Workspace decides.

## Horizon Controls

Primary filter:

```text
[ DAY ] [ SWING ] [ INVEST ]
```

The selected horizon changes the requested backend dataset and appropriate columns. It
must not cause the browser to reinterpret the same score as a different strategy.

Secondary controls may include lifecycle state, direction, freshness, watchlist,
playbook/thesis, sector, and data availability.

## Required Row/Card Content

In priority order:

1. symbol and horizon/timeframe
2. canonical lifecycle state
3. direction
4. playbook or thesis
5. market driver status/label when supplied
6. trigger and invalidation
7. tradeability state
8. options suitability and portfolio-risk state when available
9. evidence coverage
10. data freshness/evaluation timestamp

Do not fill the primary row with every indicator, Greek, factor, or rule ID.

## Row Semantics

- The lifecycle badge is always canonical or explicitly `LEGACY` during migration.
- A row with partial downstream data remains discoverable if upstream stages are valid.
- `BLOCKED`, `NO_SETUP`, and other terminal outcomes can be included by filter but are
  not presented as actionable trades.
- `TRIGGERED` is not equivalent to `TRADEABLE`.
- `TRADEABLE` is not equivalent to `PORTFOLIO_APPROVED`.
- Freshness uses the evaluation and dependency timestamps; browser receipt time is not
  substituted for market `data_as_of`.

## Primary Actions

- Select a row/card to open Trade Workspace with symbol, horizon, timeframe, and the
  canonical evaluation identifier/timestamp.
- Open compact WHY/provenance without leaving the list.
- Filter and sort.
- Add/remove a watchlist item only after a durable watchlist contract exists.

No buy/sell/order control belongs on Opportunities.

## Views

### List (default)

Dense comparison optimized for active triage. Columns remain stable; less important
fields collapse at smaller widths.

### Cards

Useful for mobile and small candidate sets. Each card still leads with state, trigger,
invalidation, and freshness.

### Heatmap

A visualization mode over the same canonical dataset. Color may represent a selected,
labeled field but may not imply lifecycle state by itself.

## Empty and Partial States

- **No candidates:** “No opportunities meet the current canonical filters.” Do not add
  fallback candidates.
- **Provider unavailable:** preserve any valid stored/partial results and identify the
  missing dependency.
- **Low setup count:** show the observed count; do not suggest looser rules.
- **Legacy-only candidate:** label source and prevent it from masquerading as V2.

## Data Contract Direction

The future endpoint should return server-owned opportunity records referencing a
canonical evaluation, rather than requiring the UI to derive candidates from movers.
Each record should include:

- stable opportunity/evaluation identifier
- `pipeline_version` and publication state
- symbol, horizon, timeframe, evaluation timestamp
- lifecycle state and relevant stage summaries
- trigger/invalidation
- evidence coverage and reason codes
- dependency freshness summary
- optional market-driver summary supplied by its future engine

## Migration Inputs

- `QXInstitutionalScanner`: reuse filter/table interaction patterns, not client-side
  scoring as canonical truth.
- `MoversWorkspace` / `MarketMovers`: reuse discovery presentation as a noncanonical
  market-movement input until a canonical opportunity API exists.
- `ReferenceRanking`: reuse for sector/relative-strength context and INVEST discovery.
- `QXOptionsScanner`: legacy-only comparison until canonical option-expression data is
  integrated by opportunity record.
- `QXOptionsIdeas`: move exploratory modeling to Research.

## Acceptance Criteria for Future Build

- One Opportunities destination supports all three horizons.
- Every canonical row opens the same Trade Workspace lifecycle.
- No client-generated fallback opportunity appears as canonical.
- Terminal and partial states remain honest and inspectable.
- Desktop, laptop, tablet, and mobile preserve state/trigger/risk priority.
