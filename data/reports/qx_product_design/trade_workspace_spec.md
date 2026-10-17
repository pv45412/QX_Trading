# Trade Workspace Specification

## Purpose

Trade Workspace is the single decision page for one symbol and one canonical
evaluation. It preserves the approved `QXLifecyclePanel` semantics and makes that
lifecycle the spine of the page. Legacy terminal and scanner states may appear only as
clearly labeled supporting context during migration; they never override `core_v1`.

## Five Questions Above the Fold

The first viewport must answer:

1. **What is happening?** Market/session context and future market-driver summary.
2. **What does QX see?** Current canonical state, direction, regime, and playbook.
3. **What are we waiting for?** The next lifecycle gate or trigger condition.
4. **Where is QX wrong?** Invalidation level/condition and terminal reason when present.
5. **Is there a trade?** Tradeability, options suitability, and portfolio decision,
   including explicit unavailable states.

## Information Hierarchy

### A. Decision Summary

Primary content:

- symbol, horizon, timeframe, evaluation timestamp, and `pipeline_version`
- current lifecycle state and plain-language meaning
- direction and primary playbook/thesis
- one explicit next action: monitor, wait for trigger, inspect failed gate, review risk,
  or no current action
- publication state and freshness warning when material

The next action must be supplied by deterministic mapping from canonical states, not
from a second trading model.

### B. Market Driver

- primary driver label
- secondary drivers
- strength and persistence
- confirming/conflicting evidence counts
- coverage and availability

Until a backend driver contract exists, render `UNAVAILABLE`; do not derive a driver
from regime, news, color, or direction in the client.

### C. Lifecycle

Reuse the approved path:

```text
WATCH -> ARMED -> TRIGGERED -> TRADEABLE -> OPTIONS_SUITABLE -> PORTFOLIO_APPROVED
```

Show valid alternate/terminal states without placing them on the happy-path rail:

`NO_SETUP`, `BLOCKED`, `NOT_TRADEABLE`, `OPTIONS_NOT_SUITABLE`,
`PORTFOLIO_VETOED`, and `EXPIRED`.

The page may make the rail more prominent, but it must not alter state names,
progression, or backend meaning.

### D. Structure / Regime / Direction

Primary view shows readable summaries:

- structure bias and meaningful BOS/CHoCH/swing context when available
- trend, volatility, gamma, and session regime
- direction label, score, evidence coverage, and coverage status
- timeframe/source labels for multi-timeframe evidence

Raw factor names, rule IDs, weights, and calculation details belong in WHY/Audit.

### E. Trigger / Invalidation / Targets

- planned trigger level and condition
- confirmation status and event timestamp
- invalidation level and condition
- structural targets and R:R when canonical outputs provide them
- clear distinction among `PLANNED`, `UNCONFIRMED`, and `CONFIRMED`

Never label a planned trigger as triggered. Missing values remain unavailable.

### F. Participation / Tradeability

- state
- participation score and evidence coverage
- spread/liquidity/RVOL-related evidence only when supplied
- structural R:R
- observed entry reference when supplied
- failed gates/reasons in user language

`NOT_TRADEABLE` retains all valid upstream evidence and trigger details.

### G. Options Expression

- suitability state
- primary canonical strategy and expiration
- candidate count
- max loss/max profit where available
- data freshness and reason codes

Exploratory modeled options remain a Research tool. They cannot be shown as the
canonical expression without canonical provenance.

### H. Portfolio Risk

- `PORTFOLIO_APPROVED`, `PORTFOLIO_VETOED`, `BLOCKED`, or unavailable state
- binding constraint
- approved quantity/contract cap when supplied
- account snapshot freshness and partial-evidence status
- concentration, exposure, and sector-provenance warnings relevant to the candidate

No raw account number, token, or secret appears in the page or telemetry.

### I. WHY / Evidence

Expandable secondary content:

- reason codes translated to concise labels, with canonical codes available in audit
- evidence grouped by Structure, Regime, Direction, Playbook, Trigger, Tradeability,
  Options, Portfolio, and Pipeline
- complete `RuleResult` fields, provenance, timestamps, stage availability, and latency
- request and evaluation timestamps
- dependency `data_as_of`, freshness, publication state, and synchronization status

Stable canonical evidence remains distinct. The presentation must not merge separate
observations solely because they share a rule ID.

### J. Future Execution Readiness

Show a disabled/read-only checklist only when the product team later approves this
surface. It is downstream of `PORTFOLIO_APPROVED` and does not mean an order exists.
See `execution_handoff_spec.md`.

## State-to-Primary-Message Contract

| State | Primary message | Primary next action |
|---|---|---|
| `NO_SETUP` | No qualifying setup | Return to Opportunities or continue monitoring |
| `WATCH` | Potential setup developing | Monitor required setup evidence |
| `ARMED` | Setup complete; trigger pending | Watch trigger and invalidation conditions |
| `TRIGGERED` | Trigger confirmed | Review tradeability gates |
| `NOT_TRADEABLE` | Triggered but tradeability failed | Inspect failed gate; do not promote |
| `TRADEABLE` | Underlying tradeability passed | Review options and portfolio stages |
| `OPTIONS_NOT_SUITABLE` | No suitable canonical options expression | Preserve underlying result; inspect reasons |
| `OPTIONS_SUITABLE` | Canonical options expression available | Review portfolio impact |
| `PORTFOLIO_VETOED` | Portfolio constraint blocks candidate | Inspect binding constraint |
| `PORTFOLIO_APPROVED` | Canonical risk gate passed | Show future readiness as informational only |
| `BLOCKED` | Required evidence unavailable or invalid | Inspect dependency/provenance and System health |
| `EXPIRED` | Setup expired | Return to Opportunities or historical review |

## Responsive Priority

- **Desktop:** summary + lifecycle + invalidation in the first viewport; two-column
  supporting sections; WHY spans full width.
- **Laptop:** same order with fewer columns; no horizontal lifecycle scrolling required.
- **Mobile:** sticky identity/state summary, vertical lifecycle, trigger/invalidation
  before charts, downstream sections collapsed by default, WHY last.

## Data and Error Semantics

- The V2 response remains the source of truth.
- `null`, empty, false, and zero retain their canonical distinctions in audit data.
- Skipped latency displays as unavailable/skipped, never `0 ms`.
- Partial account/options data does not erase valid upstream stages.
- Provider or evaluation errors fail visibly without falling back to legacy state.
- Any legacy comparison is visually isolated and cannot change the canonical outcome.

## Non-Goals

- No Phase 11 implementation.
- No order ticket, submission, paper order, or broker write.
- No frontend market-driver inference.
- No trading-rule, threshold, or lifecycle change.
- No replacement of `QXLifecyclePanel` semantics.
