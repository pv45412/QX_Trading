# QX Track 2 Milestone Report

Date: 2026-09-16

## Scope Status

- Track 2D — PASS
- Track 2B — PASS
- Track 2A — PASS
- Track 2F — PASS
- Phase 11 — NOT STARTED

## Track 2D — Provider and Snapshot Contracts

- Canonical option-chain and read-only account snapshot contracts are integrated with point-in-time visibility controls.
- Live visibility requires both `data_as_of <= evaluation_timestamp` and `provider_retrieved_at <= evaluation_timestamp`.
- Historical replay cannot consume snapshots retrieved after its fixed evaluation timestamp.
- Account persistence excludes broker credentials and raw account numbers.
- Sector provenance uses explicit KNOWN / UNKNOWN / UNAVAILABLE semantics. Incomplete sector provenance remains PARTIAL and fails closed where concentration is a hard gate.
- Phase 9/10 semantic Greek availability and canonical sector taxonomy passed Architecture, Quant, and QA review.

## Track 2B — Replay and Signal Validation

- Historical replay uses the same canonical `run_pipeline()` as live V2 evaluation.
- Replay persistence records lifecycle observations, transitions, `signal_r`, conditional `tradeability_r`, MAE, MFE, timing, invalidation, and segmentation dimensions.
- Outcome repair preserves setup identity across WATCH → ARMED, applies invalidation precedence, caps target MFE, and separates lifecycle end from session/dataset end.
- Bounded replay artifact: `data/reports/track2_replay_spy_bounded.json`.
- Bounded result: 60 input bars, 50 warmup bars, 10 canonical observations, 0 transitions, 0 outcomes, all NO_SETUP, runtime 3.57 seconds.
- The prior 250-bar baseline produced 200 observations and 0 setups/transitions. This remains an observation only; no thresholds or research rules were changed.
- Missing historical options/account snapshots remain explicit downstream UNAVAILABLE/SKIPPED states and do not invalidate upstream replay.

## Track 2A — V2 Frontend Adapter

- Feature flag `qx_v2_ui_enabled` remains OFF by default.
- Canonical client uses `POST /api/v2/qx/evaluate/{symbol}`.
- The adapter covers all lifecycle and terminal states, explicit trigger confirmation, stage availability, latency, freshness, provenance, and complete structured Trigger RuleResult evidence.
- Trigger RuleResult identity uses typed raw-source encoding before presentation normalization, preserving distinctions among undefined, null, empty string, zero, and false.
- Legacy terminal detail acquisition has one request owner; symbol changes clear stale prior-symbol state.
- Architecture, Data Semantics, QA, and UI/Performance gates passed.

## Track 2F — Lifecycle and WHY UI

- `QXLifecyclePanel` is the single reusable canonical lifecycle component.
- Primary flow: WATCH → ARMED → TRIGGERED → TRADEABLE → OPTIONS_SUITABLE → PORTFOLIO_APPROVED.
- Terminal states: BLOCKED, NO_SETUP, NOT_TRADEABLE, OPTIONS_NOT_SUITABLE, PORTFOLIO_VETOED, and EXPIRED.
- Stage-level status supports AVAILABLE, BLOCKED, SKIPPED, and UNAVAILABLE.
- The panel displays symbol, evaluation timestamp, pipeline version, regime, direction, playbook, trigger/invalidation, tradeability, options, portfolio, freshness, provenance, and actual per-stage latency.
- WHY groups evidence by STRUCTURE, REGIME, DIRECTION, PLAYBOOK, TRIGGER, TRADEABILITY, OPTIONS, PORTFOLIO, and PIPELINE.
- Structured rule rows preserve rule ID/version, category, required/observed values, pass/fail, severity, hard-gate status, weight, contribution, provenance, timestamps, and detail without recalculation.
- Deterministic fixture states are clearly marked `TEST / PREVIEW DATA — NOT LIVE`.
- One repair cycle corrected blocked Playbook array stage status. All four checker gates then passed.

## Visual Artifacts

- `data/reports/track2f/no_setup.png`
- `data/reports/track2f/watch.png`
- `data/reports/track2f/armed.png`
- `data/reports/track2f/triggered.png`
- `data/reports/track2f/tradeable.png`
- `data/reports/track2f/blocked.png`
- `data/reports/track2f/portfolio_vetoed.png`
- `data/reports/track2f/portfolio_approved.png`

## Validation

- Track 2F focused frontend: 50 passed.
- Full frontend: 70 passed.
- Production build: PASS, 2,196 modules transformed.
- Track 2F Playwright: 8 passed at feature OFF/ON, WHY toggle, BLOCKED, ARMED, symbol switching, and 1024/768/390 px responsive coverage.
- Canonical API/provider compatibility: 73 passed, 2 dependency deprecation warnings.
- Integration suite: 5 passed, 2 dependency deprecation warnings.
- Full maintained backend unit suite: 2,175 passed, 2 skipped, 2 dependency deprecation warnings, 0 failures, 0 collection errors.

## Known Legacy Browser Baseline

- Existing legacy `tests/workflow.test.cjs`: 1 passed, 4 failed before Track 2F review.
- Failures are holdings/retry workflow timeouts and are not counted as Track 2F regressions.
- Track 2F-specific Chromium smoke is fully green.

## Remaining Findings

- No blocking defects remain for Tracks 2D, 2B, 2A, or 2F.
- Historical replay currently has no observed setups in the bounded samples; this is not a failure and no rule optimization was performed.
- Historical options/account availability remains dependent on real point-in-time snapshots; no snapshots were fabricated.

## Recommended Next Work

1. Track 2C — Performance Baseline
2. Track 2E — Shadow Analysis
3. Track 2G — Legacy Migration Readiness

Human milestone approval is required before beginning any recommended next work.
