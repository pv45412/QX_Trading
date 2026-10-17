# Task Contract: MD2 Market Driver Engine Implementation

- **task_id:** MD2
- **title:** Market Driver Engine Implementation
- **current state:** COMPLETE

## Implementation Evidence

- **Engine Package:** `src/qx/market_driver/` (`models.py`, `engine.py`, `__init__.py`)
- **Approved Contract:** Option B (Continuous Multi-Factor Market Driver Decomposition with Hysteresis).
- **Parameters (`research_v1`):** Primary activation magnitude >= 35.0, secondary activation magnitude >= 20.0, strength bands (WEAK, MODERATE, STRONG), hysteresis hurdle Delta >= 10.0. Configured in `MarketDriverConfig` within `src/qx/config/rules_config.py`.
- **Pipeline Integration:** Non-authoritative stage added to `src/qx/pipeline/orchestrator.py` right after Direction. Zero lifecycle authority (cannot promote WATCH -> ARMED or veto trades).
- **Opportunity & API Parity:** `OpportunityRecord` and `OpportunityListItem` models updated to serialize `market_driver`. Frontend model adapter in `web/src/qx-v2-adapter.js` and `web/src/qx-opportunities-model.js` updated to render structured driver with truthful UNAVAILABLE fallback.
- **Verification:** 19/19 dedicated unit tests in `tests/unit/test_md2_market_driver.py` passing; 2,365 passed (0 failed) in maintained backend unit suite; 133/133 web tests passing.
- **Report:** `data/reports/md2_implementation/MD2_VERIFICATION_REPORT.md`.

## Goal

Implement the human-approved MD1 Market Driver contract as a deterministic, point-in-time-safe, observable backend capability.

## Dependencies

- MD1 is COMPLETE.
- MD1 logic and any lifecycle relationship have explicit human approval.

## In scope

- Approved engine, schemas, providers/adapters, provenance, reason codes, unavailable states, API exposure, replay support, telemetry, and bounded UI presentation integration.
- Same logic and data contract for live and historical evaluation.

## Out of scope

- Any logic, source, threshold, weight, lifecycle effect, vendor, or UI redesign not approved in MD1.
- Trading-rule optimization, execution, broker writes, and legacy deletion.

## Acceptance criteria

- Engine behavior matches the approved specification exactly.
- Inputs satisfy `data_as_of` and retrieval visibility requirements at evaluation time.
- Missing/stale inputs produce explicit unavailable/partial states and never fabricated drivers.
- Live and replay results are contract-compatible.
- Existing lifecycle behavior is unchanged unless explicitly approved in MD1.

## Required tests

- Unit tests for every driver/reason/failure state and boundary.
- Point-in-time, future-data, live/replay parity, API, and UI compatibility tests.
- Shadow-mode tests, full maintained unit suite, regression, and preflight.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- QA Gatekeeper
- UI/Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Any deviation from MD1, new driver logic, threshold/weight change, lifecycle influence, vendor, or security architecture requires explicit human approval.

## Rollback / compatibility requirements

Feature must be independently disableable, returning the prior truthful `UNAVAILABLE` state. Existing pipeline and UI contracts must remain backward compatible.

## Final deliverables

- Implemented engine and versioned contract
- Provenance and causality evidence
- Shadow and regression results
- Checker verdicts
- Disable/rollback procedure

## UI preview requirement

Any approved visible UI integration must follow `tasks/UI_PREVIEW_LOOP.md`.
