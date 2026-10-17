# Task Contract: MD1 Market Driver Engine Design

- **task_id:** MD1
- **title:** Market Driver Engine Design
- **current state:** COMPLETE

## Human Approval Record

- **Approved Date:** 2026-09-17
- **Approved Decision:** Option B — Continuous Multi-Factor Market Driver Decomposition with Hysteresis.
- **Authority Boundary:** Explanatory context only; ZERO lifecycle veto or promotion authority.
- **Coverage Contract:** Minimum 3 of 5 (Underlying + Index + at least one of Sector/Delta/Gamma). Missing underlying -> BLOCKED; missing index -> UNAVAILABLE; 3/5 or 4/5 -> PARTIAL; 5/5 -> COMPLETE.
- **Parameters (`research_v1`):** Primary activation magnitude >= 35.0; secondary activation magnitude >= 20.0; strength bands: WEAK [35, 55), MODERATE [55, 75), STRONG [75, 100]; hysteresis hurdle Delta >= 10.0. Configuration stored externally in versioned rules config.
- **Causality:** Completed candles only ($T_{\text{source\_event}} \le T_{\text{knowledge}} \le T_{\text{eval}}$). No future benchmark/sector/HTF data; no unreleased event knowledge.
- **Next Task:** MD2 Implementation authorized under Orchestrator V2.

## Goal

Design the deterministic backend-owned Market Driver contract, including data ownership, evidence, provenance, unavailable states, and its non-authoritative relationship to canonical lifecycle decisions.

## Dependencies

- BE2 is COMPLETE with approved multi-timeframe semantics.
- Existing Market Driver presentation contract remains the design baseline.

## In scope

- Driver taxonomy, source requirements, causality, evidence schema, reason codes, freshness, confidence representation, and failure states.
- Explicit decision on explanatory-only versus lifecycle influence.
- Replay/shadow validation and observability plan.
- Security, vendor, and data-availability analysis.

## Out of scope

- Production engine code, inferred placeholder drivers, threshold tuning, UI redesign, execution, and new vendors.

## Acceptance criteria

- Design identifies deterministic inputs and forbids fabricated/inferred drivers when evidence is missing.
- Point-in-time behavior and live/replay parity are specified.
- Lifecycle influence, if any, is isolated as a human decision.
- Alternatives, risks, migration, rollback, and validation strategy are documented.
- Human review approves the logic before MD2 becomes READY.

## Required tests

- No production tests required for design-only work.
- Provide executable contract examples and proposed unit, replay, integration, and causality test matrices.
- Run documentation link/consistency checks where available.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- QA/Test-Design Checker
- Product/UI Checker

## Automatic repair allowance

Maximum 3 document repair cycles. Unresolved design disagreement after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

All Market Driver logic, lifecycle influence, thresholds, new data sources/vendors, and material architecture alternatives require explicit human approval.

## Rollback / compatibility requirements

The existing truthful `UNAVAILABLE` presentation remains unchanged until MD2 is verified. No design approval authorizes implementation automatically.

## Final deliverables

- Master Design Proposal: `data/reports/md1_design/MD1_MARKET_DRIVER_PROPOSAL.md`
- Input & Current State Analysis: `data/reports/md1_design/current_state_and_input_analysis.md`
- Semantic Options: `data/reports/md1_design/semantic_options.md`
- Causality & Provenance Contract: `data/reports/md1_design/causality_and_provenance_contract.md`
- Validation & Test Plan: `data/reports/md1_design/validation_plan.md`
- UI Projection: `data/reports/md1_design/ui_projection.md`
- Risk & Architectural Analysis: `data/reports/md1_design/risk_analysis.md`

## UI preview requirement

`NOT_APPLICABLE` (Design-only phase; truthful `UNAVAILABLE` presentation preserved until MD2).

