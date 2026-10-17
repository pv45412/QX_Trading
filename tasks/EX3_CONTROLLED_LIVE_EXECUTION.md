# Task Contract: EX3 Controlled Live Execution

- **task_id:** EX3
- **title:** Controlled Live Execution
- **current state:** BACKLOG

## Goal

Enable narrowly bounded live execution only after explicit human authorization and verified safety, security, operational, and rollback controls.

## Dependencies

- EX2 is COMPLETE with accepted paper/shadow evidence.
- EX0 and EX1 controls remain verified.
- Explicit human approval grants defined live broker-write permissions and limits.

## In scope

- Only the approved accounts, instruments, order types, size/notional limits, hours, rate limits, approvals, and monitoring.
- Real-time kill switch, reconciliation, alerts, audit, incident response, and rollback.
- Staged rollout with explicit go/no-go checkpoints.

## Out of scope

- Unattended scope expansion, new strategies, new vendors, unapproved order types/accounts, threshold optimization, leverage expansion, or legacy deletion.

## Acceptance criteria

- Written live authorization defines exact permissions, limits, responsible operators, and expiration/review date.
- Fail-closed eligibility, duplicate prevention, reconciliation, alerts, and kill switch are independently verified.
- Initial rollout limits and stop conditions are enforced in code and operations.
- Every order and state transition is auditable and attributable without exposing secrets.
- No automatic expansion occurs after successful operation.

## Required tests

- Full paper/shadow replay immediately before go-live.
- Security and permission audit, failure injection, kill-switch drill, reconciliation drill, and disaster rollback test.
- Full unit/integration/regression/preflight suites and controlled canary checklist.

## Required checker roles

- Architecture Checker
- Quant/Risk Semantics Checker
- Security Checker
- QA Gatekeeper
- Operations/Performance Checker
- Independent Human Approver

## Automatic repair allowance

Maximum 3 automatic repair cycles before live authorization. Any live-safety blocker, authorization ambiguity, or remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Live broker writes, accounts, limits, credentials, security architecture, vendors, trading semantics, thresholds, and every rollout expansion require explicit human approval.

## Rollback / compatibility requirements

One-action kill switch and tested rollback to read-only mode are mandatory. Live permissions must be revocable without affecting research, canonical evaluation, Portfolio, Journal, or historical audit records.

## Final deliverables

- Signed/recorded live authorization scope
- Verified live controls and deployment package
- Canary and incident-response runbooks
- Full test/security/checker evidence
- Post-launch review schedule and rollback proof

## UI preview requirement

Any approved monitoring or control UI must follow `tasks/UI_PREVIEW_LOOP.md`.
