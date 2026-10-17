# Task Contract: EX2 Paper / Shadow Execution

- **task_id:** EX2
- **title:** Paper / Shadow Execution
- **current state:** BACKLOG

## Goal

Validate approved order-intent and execution workflows using paper or fully isolated shadow mechanisms without exposing live capital.

## Dependencies

- EX1 is COMPLETE and human-approved.
- EX0 controls, permissions, idempotency, audit, and kill-switch requirements are verified.
- The selected paper/shadow mechanism receives explicit human approval.

## In scope

- Approved simulated order intents, acknowledgements, fills, rejects, cancels, reconciliation, audit records, failure injection, and operator controls.
- Explicit separation of simulated versus live environments and records.

## Out of scope

- Live orders, live broker write permissions, automatic promotion to EX3, strategy/threshold optimization, and unapproved vendor/security changes.

## Acceptance criteria

- Every artifact is unmistakably labeled PAPER or SHADOW.
- Duplicate prevention, kill switch, reconciliation, restart recovery, rejection handling, and auditability pass.
- No live account endpoint or live order permission is reachable.
- Promotion criteria and observed failure rates are documented without changing trading rules.

## Required tests

- End-to-end paper/shadow scenarios for submit, reject, cancel, partial fill, full fill, duplicate, timeout, reconnect, and recovery.
- Permission isolation and proof that live endpoints are unreachable.
- Security, concurrency, idempotency, audit, regression, and preflight tests.

## Required checker roles

- Architecture Checker
- Quant/Risk Semantics Checker
- Security Checker
- QA Gatekeeper
- Operations/Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Any broker write access, paper-vendor selection, credential/security change, execution behavior, or progression to live trading requires explicit human approval.

## Rollback / compatibility requirements

Paper/shadow infrastructure must be isolated, disableable, and incapable of silently switching to live. Preserve all audit records and documented teardown steps.

## Final deliverables

- Isolated paper/shadow execution system
- Scenario and failure-injection results
- Permission-isolation evidence
- Operator/kill-switch runbook
- Checker verdicts and human review package

## UI preview requirement

Any approved operator-control UI must follow `tasks/UI_PREVIEW_LOOP.md`.
