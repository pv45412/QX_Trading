# Phase 8 Tradeability Implementation Plan

## Technical Goal and Requirements

Complete Phase 8 as an underlying-only tradeability assessment that consumes a validated `TriggeredSetupResult` plus current deterministic market evidence.

Phase 8 will:

- Evaluate only setups whose signal state is `TRIGGERED`.
- Return only `TRADEABLE`, `NOT_TRADEABLE`, `EXPIRED`, or `BLOCKED`.
- Keep participation independent from Direction Score.
- Enforce publication, setup validity, freshness, trigger age, extension, gap, spread/liquidity, structural R:R, and configured participation gates.
- Preserve Delta provenance and reliability.
- Use the observed underlying price as the entry reference without representing a fill.
- Exclude options expression, portfolio/account risk, position sizing, order routing, execution eligibility, lifecycle, and outcome calibration.

## Component Impact and File Demarcations

- `src/qx/tradeability/models.py`: authoritative Phase 7 input, evidence timestamps, lifecycle fields, and Phase 8 invariants.
- `src/qx/tradeability/engine.py`: trigger-state, invalidation, source-validity, freshness, timing, extension, gap, spread, R:R, and participation gates.
- `src/qx/tradeability/rvol.py`: same-slot baseline construction, validation, empirical percentile, and keyed cache.
- `src/qx/config/rules_config.py`: configurable evidence freshness, trigger age, participation, RVOL, extension, gap, spread, and R:R assumptions.
- `src/qx/config/rules_config_v1.json`: versioned Phase 8 research configuration.
- `src/qx/config/rules_config_v1.yaml`: YAML mirror of the Phase 8 configuration.
- `src/qx/signals/smc_rules_engine.py`: isolate the Phase 8 boundary and remove unapproved later-phase behavior from the modified pipeline.
- `tests/unit/test_phase8_tradeability.py`: deterministic unit and invariant coverage.
- `tests/unit/test_phase8_characterization.py`: playbook replay evidence.
- `walkthrough.md`: implementation and verification evidence.

## Data Schema and API Contracts

- Public evaluation accepts a `TriggeredSetupResult` and a separate immutable current-market evidence object.
- Setup identity, playbook, direction, trigger, invalidation, source validity, gap metadata, and publication state come from Phase 7.
- Quote, completed-bar evidence, ATR, RVOL, Delta, spread, structural targets, and freshness timestamps come from shared deterministic context.
- The result uses `observed_entry_reference_price`; no `fill_price`, option contract, account, sizing, or execution fields are allowed.
- `trade_state` remains exactly `NONE - OPTIONS EXPRESSION NOT YET EVALUATED`.

## Risk Drivers and Edge Cases

- A bullish price at or below invalidation and a bearish price at or above invalidation must be permanently `NOT_TRADEABLE`.
- A non-`TRIGGERED`, structurally invalid, trigger-invalid, expired, or stale setup must fail closed.
- Same-slot RVOL data must not be reused across symbols, timeframes, slots, or incompatible lookbacks.
- Missing Delta must not fabricate evidence; stale or low-quality Delta must lose configured reliability.
- Missing bid/ask remains `UNKNOWN` and never fabricates a spread.
- No structural target or non-positive directional risk fails the R:R gate.
- High participation never overrides a failed hard gate.
- Same-bar evaluation cannot use evidence before it becomes knowable.

## Verification

1. Run dedicated Phase 8 unit and characterization tests.
2. Run Phase 0-8 maintained regression tests.
3. Run the full `tests/unit/` suite with an isolated writable temp directory.
4. Run `pytest tests/regression/` when present.
5. Run `python -m qx.tools.run_preflight_checks`.

Phase 8 is complete only when the new tests pass, maintained regressions remain green, no prohibited post-Phase-8 behavior remains in the Phase 8 path, and Phase 9 has not begun.
