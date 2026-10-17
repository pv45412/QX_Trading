# Task Contract: BE2 Multi-Timeframe Context Contract

- **task_id:** BE2
- **title:** Multi-Timeframe Context Contract
- **current state:** COMPLETE

## Goal

Define a deterministic point-in-time contract for using and presenting multiple timeframes without silently changing canonical lifecycle or trading meaning.

## Dependencies

- BE1 is COMPLETE.
- Canonical opportunity identity and provenance contracts are stable.
- Human review of multi-timeframe semantics required before implementation begins.

## In scope

- Explicit timeframe roles, timestamp alignment, freshness, provenance, and missing-data states.
- Rules for which timeframe owns evaluation versus explanatory context.
- Contract versioning and API/schema representation.
- Historical replay and live evaluation compatibility.

## Out of scope

- Unapproved timeframe weighting, voting, confirmation, veto, thresholds, or lifecycle promotion.
- Market Driver logic, strategy optimization, execution, and vendor changes.

## Acceptance criteria

- A human-approved semantic specification exists before implementation.
- Every consumed bar satisfies point-in-time visibility for the evaluation timestamp.
- Timeframes cannot be mixed without labels, provenance, and deterministic alignment.
- Missing or stale higher/lower timeframe context remains explicit and cannot fabricate confidence.
- Replay and live paths use the same approved contract.

## Required tests

- Timestamp alignment, market-calendar, DST, stale/missing, and future-data exclusion tests.
- Live/replay parity and serialization tests.
- Pipeline and opportunity-service regression.
- Full maintained unit suite and preflight.

## Required checker roles

- Architecture Checker
- Quant/Data Semantics Checker
- QA Gatekeeper
- Performance Checker

## Automatic repair allowance

Maximum 3 automatic repair cycles after human approval of semantics. A remaining blocker after cycle 3 sets `HUMAN_REQUIRED`.

## Human gate conditions

All multi-timeframe rule definitions, weights, confirmations, vetoes, or changes to trading semantics require explicit human approval before coding.

## Rollback / compatibility requirements

Contract must be versioned and additive. Rollback restores single-timeframe canonical behavior without rewriting historical observations.

## Final deliverables

- Human-approved multi-timeframe specification
- Versioned schemas and sequence diagrams
- Live/replay compatibility evidence
- Test and checker reports
- Rollback plan

## UI preview requirement

If visible UI changes enter approved scope, follow `tasks/UI_PREVIEW_LOOP.md`; otherwise record `NOT_APPLICABLE`.
