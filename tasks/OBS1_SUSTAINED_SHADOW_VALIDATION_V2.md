# Task Contract: OBS1 Sustained Shadow Validation v2

- **task_id:** OBS1
- **title:** Sustained Shadow Validation v2
- **current state:** COMPLETE

## Goal

Observe canonical `core_v1` behavior over a sustained representative period, including opportunity, multi-timeframe, and Market Driver contracts, without execution or automatic rule optimization.

## Dependencies

- MD2 is COMPLETE.
- BE1 and BE2 are COMPLETE.
- Persistent shadow telemetry is healthy and privacy-safe.

## In scope

- Live read-only observations, lifecycle transitions, reason distributions, evidence coverage, freshness, provider quality, stage latency, and contract availability.
- Segment results by symbol, timeframe, regime, direction, playbook, and evidence coverage.
- Record low/zero transition counts as findings.

## Out of scope

- Orders, paper orders, threshold changes, rule optimization, manufactured observations/outcomes, and provider substitution.

## Acceptance criteria

- Observation window, symbol universe, cadence, outages, and coverage are fully documented.
- Transition and terminal-state counts are reproducible from persistent telemetry.
- Missing data and unavailable downstream stages remain explicit.
- No live user response is blocked by shadow telemetry failure.
- Findings separate data quality, logic behavior, and performance without changing rules.

## Required tests

- Shadow persistence, fail-open, privacy/redaction, transition, and aggregation tests.
- Live/replay identity and point-in-time checks.
- Full maintained unit suite, API/integration regression, and preflight.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- QA Gatekeeper
- Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles for observation tooling defects. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Trading-rule, threshold/weight, multi-timeframe, Market Driver, vendor, security, or execution changes discovered during observation require separate explicit human approval.

## Rollback / compatibility requirements

Shadow collection must fail open and be independently disableable without changing canonical API responses or deleting telemetry.

## Final deliverables

- Sustained observation dataset and provenance manifest
- Lifecycle/terminal-state distributions
- Data-quality and latency findings
- Test/checker report
- Human-reviewed recommendations with no automatic rule changes

## UI preview requirement

If visible UI changes enter approved scope, follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.
