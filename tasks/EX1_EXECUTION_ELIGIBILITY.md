# Task Contract: EX1 Execution Eligibility Engine

- **task_id:** EX1
- **title:** Execution Eligibility Engine
- **current state:** BACKLOG

## Goal

Implement the approved EX0 read-only eligibility decision that determines whether a canonical setup may proceed to an order-intent stage, without placing orders.

## Dependencies

- EX0 is COMPLETE and human-approved.
- Eligibility semantics and risk ownership are explicitly approved.

## In scope

- Versioned eligibility input/output contract, deterministic reason codes, vetoes, permissions, freshness, idempotency, telemetry, and read-only API exposure.
- Integration with canonical lifecycle, options suitability, and portfolio-risk outputs exactly as approved.

## Out of scope

- Order creation/submission, broker writes, paper/live fills, unapproved thresholds/weights, and execution UI controls.

## Acceptance criteria

- Eligibility never follows solely from `TRADEABLE` or `PORTFOLIO_APPROVED` state.
- Missing, stale, partial, unauthorized, or inconsistent inputs fail closed with explicit reasons.
- No broker-write capability exists in the engine or API.
- Results are deterministic, versioned, auditable, and point-in-time safe.

## Required tests

- Unit tests for every eligibility/veto/permission/freshness state.
- Point-in-time, idempotency, API authorization, and no-broker-write tests.
- Pipeline, options, portfolio, full unit, regression, and preflight tests.

## Required checker roles

- Architecture Checker
- Quant/Risk Semantics Checker
- Security Checker
- QA Gatekeeper
- Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Eligibility rules, thresholds, weights, vetoes, permissions, security changes, and all progression toward broker writes require explicit human approval.

## Rollback / compatibility requirements

Eligibility must be feature-gated and independently disableable. Disabling it restores the prior read-only system with no canonical lifecycle changes.

## Final deliverables

- Eligibility engine and versioned contract
- Reason-code and permission documentation
- Security/no-write proof
- Test/checker evidence
- Disable/rollback runbook

## UI preview requirement

If visible UI changes enter approved scope, follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.
