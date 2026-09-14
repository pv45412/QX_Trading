# Phase 3 — Signal Quality & Validation Walkthrough

## Summary of Completed Engineering Work

Phase 3 transitions the QX Platform from structural plumbing and fail-closed safety to empirical decision validation.

All 7 core focus areas have been successfully implemented and verified with automated test suites:

### 1. Real Option-Chain Integration (`chains.py`, `schwab/options.py`)
- Extended `OptionContract` in [`chains.py`](file:///c:/Project/2026/src/qx/options/chains.py) to support native Option Greeks (`delta`, `gamma`, `theta`, `vega`).
- Connected `SchwabOptionsChainProvider` and `OptionsChainProvider` protocol to allow direct passthrough of live option chains to trade construction.
- `/api/options-scanner/ideas` returns `publication_state: VERIFIED` only when backed by live option chains, or `SIMULATED` (`executable: False`) when using modeled contracts for research.

### 2. Multi-Factor Historical Signal Validation (`validator.py`)
- Built `SignalValidator` in [`validator.py`](file:///c:/Project/2026/src/qx/signals/validator.py) enforcing multi-factor technical alignment:
  - **BOS / CHoCH**: Break of Structure & Change of Character.
  - **RVOL**: Relative Volume expansion ($RVOL \ge 1.5$).
  - **VWAP**: Positioning relative to intraday volume-weighted average price.
  - **Macro / Sector**: Fair Value Gap proximity and sector relative strength.
- Outputs composite `SignalQualityScore` ($0-100$) and status (`VALIDATED`, `WEAK_ALIGNMENT`, `INVALIDATED`).

### 3. Walk-Forward Testing Protocol (`walk_forward.py`)
- Extended [`walk_forward.py`](file:///c:/Project/2026/src/qx/backtesting/walk_forward.py) with `evaluate_walk_forward_metrics()` to compute:
  - Out-of-Sample Win Rate and Profit Factor.
  - Expectancy Decay Ratio ($E_{\text{OOS}} / E_{\text{IS}}$).
  - Flags strategies as `OVERFITTED` if out-of-sample performance degrades below $50\%$ of in-sample expectancy.

### 4. Portfolio-Aware Trade Scoring (`veto_service.py`)
- Added `check_portfolio_risk()` in [`veto_service.py`](file:///c:/Project/2026/src/qx/options_scanner/services/veto_service.py).
- Vetoes trade ideas that push total portfolio sector exposure beyond configurable risk limits ($25\%$).

### 5. Trade Lifecycle Validation (`lifecycle.py`)
- Created `TradeLifecycleRecord` in [`lifecycle.py`](file:///c:/Project/2026/src/qx/execution/lifecycle.py) tracking full state machine transitions:
  `PROPOSED` → `PENDING_ENTRY` → `ACTIVE` → `PARTIAL_TARGET` → `STOPPED_OUT` / `TARGET_REACHED` / `EARLY_EXIT` / `EXPIRED`.
- Captures entry slippage, holding duration in hours, and realized R-multiple outcomes.

### 6. Signal Score Calibration Engine (`calibration.py`)
- Created [`calibration.py`](file:///c:/Project/2026/src/qx/signals/calibration.py) calculating score bucket win rates (`Tier 1: 80-100`, `Tier 2: 60-79`, `Tier 3: 0-59`), overall Brier calibration score, and monotonic win-rate validation.

### 7. Latency and Freshness Verification (`freshness.py`)
- Created [`freshness.py`](file:///c:/Project/2026/src/qx/signals/freshness.py) to check quote timestamps against operational limits (max 5s for intraday, 60s for swing setups).
- Rejects operationally stale proposals with `STALE_BLOCKED`.

---

## Verification Results

### Unit Test Execution
All 16 unit tests across Phase 2 Hardening and Phase 3 Signal Quality pass 100%:

```
tests/unit/test_phase2_hardening.py::test_dynamic_basis_tracking_order_router PASSED
tests/unit/test_phase2_hardening.py::test_ampm_gex_segregation PASSED
tests/unit/test_phase2_hardening.py::test_atomic_basis_from_quotes PASSED
tests/unit/test_phase2_hardening.py::test_gex_missing_settlement_type_0dte_fallback PASSED
tests/unit/test_phase2_hardening.py::test_price_normalization_decoupled PASSED
tests/unit/test_phase2_hardening.py::test_put_credit_spread_requires_valid_long_put PASSED
tests/unit/test_phase2_hardening.py::test_payoff_topology_analytical_legs PASSED
tests/unit/test_phase2_hardening.py::test_options_ideas_simulated_gating_and_no_fallback_prices PASSED
tests/unit/test_phase2_hardening.py::test_telemetry_zero_observations_returns_none PASSED
tests/unit/test_phase2_hardening.py::test_order_router_fail_closed_execution_eligibility PASSED
tests/unit/test_phase3_signal_quality.py::test_multi_factor_signal_validator PASSED
tests/unit/test_phase3_signal_quality.py::test_walk_forward_oos_expectancy_evaluation PASSED
tests/unit/test_phase3_signal_quality.py::test_portfolio_sector_risk_veto PASSED
tests/unit/test_phase3_signal_quality.py::test_trade_lifecycle_state_transitions PASSED
tests/unit/test_phase3_signal_quality.py::test_signal_score_calibration PASSED
tests/unit/test_phase3_signal_quality.py::test_freshness_latency_checker PASSED
```
