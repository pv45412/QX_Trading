# Portfolio Specification

## Product Definition

Portfolio is the read-only brokerage account and position-risk destination. It is not
ETF constituent research. The current `Holdings` component must be renamed and moved to
Research as **ETF Constituents** or **Fund Holdings Research**.

## Primary User Jobs

- inspect accounts and positions
- understand P/L and directional/sector exposure
- identify concentration and open-trade risk
- understand supported Greeks and portfolio constraints
- find positions requiring attention
- see how a candidate affects portfolio risk

## Information Hierarchy

### Account Summary

- hashed/internal account identifier and user-safe label
- snapshot timestamp, freshness, publication state, and provider health
- balances required by the approved risk engine
- warning when data is partial, stale, or unavailable

Never display or persist raw broker account numbers, credentials, or tokens.

### Positions

- symbol/instrument, quantity, market value, cost/P&L when supplied
- asset class and sector with explicit provenance status
- linked canonical setup/trade record when one exists
- position-level risk and attention reason

### Exposure and Concentration

- gross/net exposure where supported
- sector and single-name concentration
- option/Greek exposure where supported
- open risk relative to approved portfolio limits
- provenance/coverage for every concentration category

Unknown sector data is not an `Unassigned` approval bucket. If a required position has
unknown or unavailable sector provenance, the concentration view and associated risk
evidence remain `PARTIAL`; required hard gates fail closed under `research_v1`.

### Constraints and Candidate Impact

- portfolio-risk decision
- binding constraint
- approved contract/quantity cap when supplied
- candidate impact compared with current exposure
- reason codes and evidence in expandable audit

### Positions Requiring Attention

Exception list for:

- breached or near-binding constraints
- invalidation/monitor condition reached
- stale or partial account evidence
- unsupported/unknown sector provenance affecting analysis
- material option/Greek risk when available

## Allowed Actions

- select account and position
- open linked Trade Workspace or Research
- refresh read-only account snapshot
- expand risk evidence and provenance
- filter positions requiring attention

No order entry, close/roll action, broker write permission, or Phase 11 behavior.

## Brokerage Portfolio vs ETF Research

| Concept | Portfolio | Research |
|---|---|---|
| Object | Actual broker account position | ETF/fund constituent |
| Quantity/value | User account data | Fund weight |
| P/L | Account position P/L | Not applicable |
| Concentration | User portfolio risk | Fund composition research |
| Sector provenance | Risk-gating input | Descriptive research field |
| Canonical risk decision | Yes, when context exists | No |
| Current `Holdings` component | No | Yes, renamed |

## Availability Semantics

- Account absent: Portfolio shell explains that no canonical read-only snapshot exists.
- Snapshot stale: show age and the risk engine’s freshness state.
- Snapshot partial: show valid fields, mark affected calculations partial, and identify
  missing provenance.
- Risk stage skipped: display `SKIPPED`, not approval and not zero latency.
- Provider error: preserve last valid snapshot only if the canonical contract labels its
  timestamp and staleness; never imply it is current.

## Future Acceptance Criteria

- One shared account source serves Portfolio and canonical Phase 10 risk.
- Account identifiers are internal/hashed throughout UI telemetry and persistence.
- ETF constituent data cannot be mistaken for account holdings.
- Candidate-to-portfolio navigation preserves the canonical evaluation identity.
- Partial provenance cannot appear as a completed risk pass.
