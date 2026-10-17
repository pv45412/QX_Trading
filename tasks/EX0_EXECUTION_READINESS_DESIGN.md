# Task Contract: EX0 Phase 11 Execution-Readiness Design

- **task_id:** EX0
- **title:** Phase 11 Execution-Readiness Design
- **current state:** BACKLOG

## Goal

Design Phase 11 boundaries, permissions, auditability, safety controls, failure handling, and rollout stages without placing or simulating orders.

## Dependencies

- PERF2 is COMPLETE.
- OBS1 evidence is accepted.
- Existing `src/qx/execution` remains ADAPT / REVIEW until this design is approved.

## In scope

- Execution state machine proposal, eligibility boundary, order intent schema, permission model, idempotency, kill switch, reconciliation, audit log, recovery, and staged rollout design.
- Threat model and broker capability assessment using existing vendors only unless separately approved.

## Out of scope

- Production execution code, paper/live orders, broker writes, credential changes, or eligibility/trading-rule implementation.

## Acceptance criteria

- Design separates canonical evaluation, eligibility, order intent, submission, acknowledgement, fill, and outcome.
- Fail-closed controls, duplicate-order prevention, kill switch, reconciliation, and rollback are specified.
- No component can infer permission from lifecycle state alone.
- Security, operational, legal/compliance, and human-control risks are documented.
- Human approval is recorded before EX1 becomes READY.

## Required tests

- No execution tests are run because implementation is prohibited.
- Provide proposed state-machine, idempotency, failure-injection, security, reconciliation, and rollback test matrices.
- Run documentation consistency checks where available.

## Required checker roles

- Architecture Checker
- Quant/Risk Semantics Checker
- Security Checker
- QA/Test-Design Checker
- Operations Checker

## Automatic repair allowance

Maximum 3 document repair cycles. Unresolved design disagreement after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

All Phase 11 behavior, broker writes, permissions, security/auth changes, vendors, and material architecture alternatives require explicit human approval.

## Rollback / compatibility requirements

No runtime path changes are allowed in EX0. Existing read-only behavior and execution placeholders remain untouched.

## Final deliverables

- Human-reviewed execution-readiness architecture
- State/permission/audit contracts
- Threat and failure-mode analysis
- Test and rollout plan
- Explicit approval or rejection record

## UI preview requirement

If visible UI prototypes enter approved scope, follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.
