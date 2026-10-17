# Structural Context Validation and Data Remediation Plan

## Goal

Explain and, only where an implementation contract is defective, repair the loss of
confirmed Phase 3 structural context before Phase 5 and Phase 6 evaluation. Preserve
all existing trading semantics, thresholds, weights, and lifecycle gates.

## Workstreams

1. Trace representative BOS, CHoCH, protected-swing, and no-event observations from
   point-in-time bars through the canonical playbook input and gate results.
2. Add deterministic adversarial tests for confirmed context, persistence,
   future-pivot exclusion, symbol/timeframe isolation, and playbook consumption.
3. Repair only confirmed schema or adapter defects between existing canonical stages.
4. Diagnose stale Schwab observations with timestamp and age distributions without
   relaxing freshness policy.
5. Probe current Schwab behavior for SPX quote, history, and option-chain symbol
   representations; retain `SPX` as the canonical QX identity.
6. Isolate unit tests from local dotenv credentials while preserving production
   runtime loading behavior.
7. Profile repeated replay prefixes and report optimization candidates without
   implementing performance changes.

## Contract Boundaries

- `SMCAnalysisResult` remains the authoritative Phase 3 output.
- `run_pipeline()` remains the sole canonical live and replay orchestrator.
- Provider inputs remain point-in-time safe and must not be fabricated.
- Phase 3-10 rules, thresholds, weights, and playbook gates are unchanged.
- Phase 11, broker writes, new vendors, and destructive migration remain prohibited.

## Verification

- Focused structure, regime, direction, playbook, provider, and isolation tests.
- Independent Architecture, Quant/Data Semantics, QA, and Performance reviews.
- Full maintained unit suite and preflight/regression checks where available.
- Post-repair canonical observation distribution, with zero transitions accepted as
  a valid result.
