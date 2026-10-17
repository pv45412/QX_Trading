# Task Contract: PERF2 Structure / Pipeline Optimization

- **task_id:** PERF2
- **title:** Structure / Pipeline Optimization
- **current state:** BACKLOG

## Goal

Optimize only bottlenecks demonstrated by OBS1 while preserving canonical outputs, point-in-time behavior, and Phase 3-10 semantics.

## Dependencies

- OBS1 is COMPLETE with reproducible latency and I/O evidence.
- Optimization targets and budgets are documented.

## In scope

- Profiling, repeated-I/O reduction, algorithmic efficiency, bounded batching, serialization/query improvements, and measured frontend render/request improvements.
- Before/after p50, p95, p99, throughput, memory, and output-parity evidence.

## Out of scope

- Threshold/rule changes, semantic shortcuts, fabricated caches, new vendors, Redis/WebSockets/queues without separate architecture approval, and execution work.

## Acceptance criteria

- Every optimization maps to a measured bottleneck.
- Canonical outputs and reason codes remain equivalent for a fixed test corpus.
- Point-in-time, freshness, and stage-skipped semantics remain unchanged.
- Before/after benchmarks are reproducible and include regressions or trade-offs.

## Required tests

- Golden-output/parity tests for structure and pipeline results.
- Performance benchmarks with p50/p95/p99 and replay throughput.
- Concurrency, API, frontend request/render, full unit, regression, and preflight tests.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- QA Gatekeeper
- Performance/UI Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

Material architecture alternatives, new infrastructure/vendors, security changes, or any semantic/trading-rule change require explicit human approval.

## Rollback / compatibility requirements

Optimizations must be reversible and preserve versioned external contracts. Maintain an unoptimized parity path or reproducible baseline until verification completes.

## Final deliverables

- Profiling report and selected bottlenecks
- Optimization patch and parity evidence
- Before/after benchmark report
- Checker verdicts
- Rollback instructions

## UI preview requirement

Any visible frontend optimization must follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.
