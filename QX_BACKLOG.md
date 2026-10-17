# QX Backlog

This is the ordered milestone backlog. A backlog entry does not authorize implementation; its task contract controls scope and gates.

| Order | ID | Milestone | State | Contract | Primary gate |
|---:|---|---|---|---|---|
| 1 | UX6 | System Consolidation | COMPLETE | `tasks/UX6_SYSTEM.md` | Human/product approval accepted |
| 2 | BE1 | Canonical Opportunity Service / Persistence Contract | COMPLETE | `tasks/BE1_OPPORTUNITY_SERVICE.md` | Human approval accepted; Option A DDL integrity verified; full backend suite 100% green |
| 3 | BE2 | Multi-Timeframe Context Contract | COMPLETE | `tasks/BE2_MULTI_TIMEFRAME_CONTRACT.md` | Option B approved; Factor #7 weighted HTF evidence implemented; 15/15 dedicated tests and 2,346 backend tests green |
| 4 | MD1 | Market Driver Engine Design | COMPLETE | `tasks/MD1_MARKET_DRIVER_DESIGN.md` | Human approval of Option B accepted |
| 5 | MD2 | Market Driver Engine Implementation | COMPLETE | `tasks/MD2_MARKET_DRIVER_IMPLEMENTATION.md` | Option B verified; 19/19 dedicated tests and 2,365 backend tests green |
| 6 | OBS1 | Sustained Shadow Validation v2 | COMPLETE | `tasks/OBS1_SUSTAINED_SHADOW_VALIDATION_V2.md` | Observational protocol execution; 548 observations validated; zero PIT violations |
| 7 | PERF2 | Structure / Pipeline Optimization | READY | `tasks/PERF2_STRUCTURE_PIPELINE_OPTIMIZATION.md` | Measured bottleneck evidence from OBS1 (Structure stage dominates ~98% of pipeline execution) |
| 8 | JR1 | Journal / Outcome Persistence | BACKLOG | `tasks/JR1_JOURNAL_OUTCOME_PERSISTENCE.md` | Human approval of domain/persistence model |
| 9 | EX0 | Phase 11 Execution-Readiness Design | BACKLOG | `tasks/EX0_EXECUTION_READINESS_DESIGN.md` | Human approval of execution architecture |
| 10 | EX1 | Execution Eligibility Engine | BACKLOG | `tasks/EX1_EXECUTION_ELIGIBILITY.md` | Human approval of eligibility semantics |
| 11 | EX2 | Paper / Shadow Execution | BACKLOG | `tasks/EX2_PAPER_SHADOW_EXECUTION.md` | Human approval before execution behavior |
| 12 | EX3 | Controlled Live Execution | BACKLOG | `tasks/EX3_CONTROLLED_LIVE_EXECUTION.md` | Explicit live-trading authorization |

## Backlog rules

- Only one milestone is designated `READY` unless explicitly approved for parallel work.
- A milestone may not skip its dependency, checker, or human-review gates.
- Findings may create future backlog proposals, but they may not silently expand the active milestone.
- No milestone may alter `core_v1` trading rules or thresholds without explicit human approval.
- Destructive cleanup and legacy removal remain separate human-approved work, even when a replacement is verified.
- Any milestone that modifies visible UI must follow `tasks/UI_PREVIEW_LOOP.md` before independent checker review.
