# QX Project State

Last updated: 2026-09-17

## Current control state

- Active milestone: `PERF2 Structure/Pipeline Optimization`
- Current execution status: `READY`; OBS1 Sustained Shadow Validation v2 is COMPLETE. Observational report committed at `data/reports/obs1_validation/OBS1_SHADOW_OBSERVATION_REPORT.md` and dataset at `data/reports/obs1_validation/obs1_shadow_telemetry.json`. All 548 observations validated, zero point-in-time violations, zero rule/parameter modifications applied.
- Canonical pipeline version remains `core_v1`.
- Phase 11 and broker writes remain prohibited unless an execution milestone reaches its explicit human gate.

## Completed baseline

| Baseline milestone | State |
|---|---|
| Track 2 canonical integration | COMPLETE |
| DQ/data quality milestone | COMPLETE |
| Structural-context remediation | COMPLETE |
| UX1 Trade Workspace / shell | COMPLETE |
| UX2 Opportunities | COMPLETE |
| UX3 Today | COMPLETE |
| UX3.1 front-half polish | COMPLETE |
| UX4 Portfolio | COMPLETE |
| UX5 Research | COMPLETE |
| UX6 System | COMPLETE |
| BE1 Opportunity Service | COMPLETE |
| BE2 Multi-Timeframe Contract | COMPLETE |
| MD1 Market Driver Design | COMPLETE |
| MD2 Market Driver Implementation | COMPLETE |
| OBS1 Sustained Shadow Validation v2 | COMPLETE |

Approved product flow: `Today -> Opportunities -> Trade -> Portfolio -> Research`.

Primary navigation: `Today`, `Opportunities`, `Trade`, `Portfolio`, `Research`, `System`. Journal remains secondary.

## Remaining milestone status

| Milestone | State | Dependency condition |
|---|---|---|
| BE1 Opportunity Service | COMPLETE | Human review accepted; Option A DDL integrity verified; full backend suite 100% green |
| BE2 Multi-Timeframe Contract | COMPLETE | Option B approved; Factor #7 weighted HTF evidence implemented; 15/15 dedicated tests and 2,346 backend tests green |
| MD1 Market Driver Design | COMPLETE | Human review accepted Option B; specification committed in `data/reports/md1_design/` |
| MD2 Market Driver Implementation | COMPLETE | Option B implemented; 19/19 dedicated unit tests and 2,365 backend tests green |
| OBS1 Sustained Shadow Validation v2 | COMPLETE | 548 observations across live, PIT, replay, and session simulations; zero PIT violations; report generated |
| PERF2 Structure/Pipeline Optimization | READY | OBS1 complete with measured bottlenecks (Structure stage dominates ~98% of pipeline execution time) |
| JR1 Journal/Outcome Persistence | BACKLOG | BE1 complete and persistence/domain model approved |
| EX0 Execution-Readiness Design | BACKLOG | PERF2 complete |
| EX1 Execution Eligibility | BACKLOG | EX0 human-reviewed and approved |
| EX2 Paper/Shadow Execution | BACKLOG | EX1 verified and broker-write simulation gate approved |
| EX3 Controlled Live Execution | BACKLOG | EX2 verified and explicit live-trading approval granted |

## Allowed states

`BACKLOG`, `READY`, `IN_PROGRESS`, `CHECKING`, `REPAIRING`, `VERIFIED`, `HUMAN_REVIEW`, `COMPLETE`, `BLOCKED`, `HUMAN_REQUIRED`

## State transition rules

1. `BACKLOG -> READY` only when all dependencies and prerequisite human gates are satisfied.
2. `READY -> IN_PROGRESS` requires explicit human authorization for that milestone.
3. `IN_PROGRESS -> CHECKING` occurs only after Maker evidence and required tests exist.
4. `CHECKING -> REPAIRING` occurs when any independent checker returns `BLOCK`.
5. `REPAIRING -> CHECKING` is allowed for at most three automatic repair cycles.
6. A fourth unresolved blocker becomes `HUMAN_REQUIRED`; no further automatic repair is allowed.
7. `CHECKING -> VERIFIED` requires every required checker to return `PASS`; the Maker may never self-approve.
8. `VERIFIED -> HUMAN_REVIEW` is required whenever the task contract contains a human gate.
9. `VERIFIED` or `HUMAN_REVIEW -> COMPLETE` requires the milestone acceptance criteria and applicable human approval.
10. `BLOCKED` is reserved for an external dependency that prevents progress; `HUMAN_REQUIRED` is reserved for an explicit governance decision or exhausted repair budget.

## Non-negotiable human gates

Human approval is required before changing trading semantics, thresholds, multi-timeframe semantics, Market Driver logic, persistence/domain models, destructive legacy migration, broker writes or execution, or vendor/security architecture.

## Verification authority

- Maker implements and submits evidence but never approves its own work.
- Architecture Checker reviews ownership, dependencies, legacy leakage, and architecture boundaries.
- Quant/Data Semantics Checker reviews causality, market-data meaning, trading semantics, and numerical integrity.
- QA Gatekeeper independently runs required focused and regression tests.
- UI/Performance Checker reviews responsive UX, rendering/request behavior, and measured performance where applicable.

## UI development preview policy

- Every task that modifies visible UI inherits `tasks/UI_PREVIEW_LOOP.md`.
- Preview inspection occurs after each meaningful UI slice, not only at final validation.
- Preview artifacts live under `data/reports/<task_id>/preview/` and include first, final, major-state, desktop, and mobile evidence.
- Final reports record visual issues discovered and repaired; non-UI tasks record the policy as `NOT_APPLICABLE`.

## Control files

- Backlog: `QX_BACKLOG.md`
- Roadmap and dependency graph: `QX_ROADMAP.md`
- Milestone contracts: `tasks/`
