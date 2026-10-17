# QX Roadmap

## Dependency graph

```text
UX5 Research [COMPLETE]
  -> UX6 System [COMPLETE]
      -> BE1 Canonical Opportunity Service / Persistence Contract [COMPLETE]
          -> BE2 Multi-Timeframe Context Contract [COMPLETE]
              -> MD1 Market Driver Engine Design [COMPLETE]
                  -> MD2 Market Driver Engine Implementation [COMPLETE]
                      -> OBS1 Sustained Shadow Validation v2 [COMPLETE]
                              -> PERF2 Structure / Pipeline Optimization [READY]
                                  -> EX0 Phase 11 Execution-Readiness Design
                                      -> HUMAN REVIEW
                                          -> EX1 Execution Eligibility Engine
                                              -> HUMAN REVIEW
                                                  -> EX2 Paper / Shadow Execution
                                                      -> HUMAN REVIEW
                                                          -> EX3 Controlled Live Execution
                                                              -> EXPLICIT LIVE-TRADING APPROVAL

BE1
  -> JR1 Journal / Outcome Persistence
      -> HUMAN REVIEW OF PERSISTENCE DOMAIN MODEL
```

## Stage 1: Product control surfaces

- `UX5 Research`: consolidated analytical depth; complete.
- `UX6 System`: consolidate operational status, provider health, configuration, jobs, and diagnostics without changing trading or execution behavior.

## Stage 2: Canonical opportunity contracts

- `BE1 Opportunity Service`: create one read-only canonical opportunity aggregation contract for Today and Opportunities.
- `BE2 Multi-Timeframe Contract`: define and implement explicit cross-timeframe context only after human approval of semantics.

## Stage 3: Market context

- `MD1 Market Driver Design`: specify deterministic ownership, data contract, provenance, failure states, and lifecycle relationship.
- `MD2 Market Driver Implementation`: implement only the approved design; no unapproved inference or threshold tuning.

## Stage 4: Evidence and reliability

- `OBS1 Sustained Shadow Validation v2`: observe canonical behavior and transitions over a sustained window without execution or rule optimization.
- `PERF2 Structure/Pipeline Optimization`: optimize only measured bottlenecks while preserving point-in-time and pipeline semantics.
- `JR1 Journal/Outcome Persistence`: branch after BE1 to add approved durable idea/trade/outcome records without pretending legacy views are a journal.

## Stage 5: Execution readiness

- `EX0 Execution-Readiness Design`: design controls, boundaries, auditability, permissions, and rollback; no orders.
- `EX1 Execution Eligibility`: compute read-only execution eligibility under approved semantics; no orders.
- `EX2 Paper/Shadow Execution`: exercise order workflows without live capital, only after explicit approval.
- `EX3 Controlled Live Execution`: limited live operation only after explicit human authorization, security review, and verified kill/rollback controls.

## Global governance

- Maximum automatic repair cycles per milestone: 3.
- Maker may never self-approve.
- Human approval is mandatory for trading semantics, thresholds, multi-timeframe semantics, Market Driver logic, persistence/domain models, destructive legacy removal, broker writes/execution, and vendor/security architecture.
- A recommendation or design document does not authorize implementation.
- The active task contract is the scope boundary; all other milestones remain frozen.
- Visible UI work must follow `tasks/UI_PREVIEW_LOOP.md`, with incremental desktop/mobile previews stored under the task report directory.
