# Phase 3 — Signal Quality & Validation Implementation Plan

This implementation plan outlines the architecture, data contracts, and verification protocols for **Phase 3: Signal Quality & Validation** on the QX Platform.

The objective of Phase 3 is to transition QX from structural plumbing hardening to empirical trading decision validation—ensuring that generated trade ideas use real option chains, pass historical multi-factor signal validation, score against existing portfolio risk, and maintain verified out-of-sample statistical expectancy.

---

## User Review Required

> [!IMPORTANT]
> **No Mock/Simulated Fallbacks in Live Modes**: All `/api/options-scanner/ideas` and live signal endpoints will require verified live option-chain contract data. If live option chains are unavailable from the market data provider, signals will fail closed with `publication_state: BLOCKED` or `publication_state: SIMULATED` (strictly non-executable research mode).

> [!NOTE]
> **Walk-Forward Out-of-Sample Protocol**: Backtesting will enforce strict rolling-window out-of-sample validation to prevent look-ahead bias and overfitting. Signals failing out-of-sample walk-forward checks will be demoted in signal score.

---

## Proposed Changes & Focus Areas

### 1. Real Option-Chain Integration
Eliminate synthetic Greek and formulaic contract generation in option scanning and ideas generation.

#### [MODIFY] [chains.py](file:///c:/Project/2026/src/qx/options/chains.py)
#### [MODIFY] [trade_constructor.py](file:///c:/Project/2026/src/qx/options_scanner/services/trade_constructor.py)
#### [MODIFY] [web.py](file:///c:/Project/2026/src/qx/interfaces/web.py)

- Wire `OptionsChainProvider` and `SchwabOptionsChainProvider` into `TradeConstructor` to fetch verified option chain legs, real bid/ask spreads, delta, IV, and open interest.
- Update `/api/options-scanner/ideas` to populate `publication_state: VERIFIED` only when backed by live option chains; set `publication_state: SIMULATED` and `executable: False` otherwise.

---

### 2. Multi-Factor Historical Signal Validation
Validate technical setup quality across multiple structure and volume indicators before signal publication.

#### [NEW] [validator.py](file:///c:/Project/2026/src/qx/signals/validator.py)
#### [MODIFY] [signal_service.py](file:///c:/Project/2026/src/qx/options_scanner/services/signal_service.py)

- Build `SignalValidator` verifying alignment across:
  - **BOS / CHoCH**: Break of Structure & Change of Character confirmation on higher timeframes.
  - **FVG**: Fair Value Gap proximity and fill status.
  - **VWAP & RVOL**: Volume-weighted average price positioning and relative volume expansion ($RVOL \ge 1.5$).
  - **Sector Rotation**: Sector relative strength vs SPY/QQQ benchmark.
- Generate a composite `SignalQualityScore` ($0 - 100$).

---

### 3. Walk-Forward Testing Framework
Implement out-of-sample evaluation to validate signal robustness over time.

#### [MODIFY] [walk_forward.py](file:///c:/Project/2026/src/qx/backtesting/walk_forward.py)
#### [NEW] [test_walk_forward_validation.py](file:///c:/Project/2026/tests/unit/test_walk_forward_validation.py)

- Implement rolling train/test windows (e.g. 60-day in-sample training, 20-day out-of-sample testing).
- Calculate out-of-sample metrics: Profit Factor, Win Rate, Max Drawdown, and Expectancy ratio.
- Flag signals with high in-sample performance but degraded out-of-sample metrics as "Overfitted".

---

### 4. Portfolio-Aware Trade Scoring
Integrate current portfolio holdings and sector concentration into trade scoring and veto logic.

#### [MODIFY] [veto_service.py](file:///c:/Project/2026/src/qx/options_scanner/services/veto_service.py)
#### [MODIFY] [allocator.py](file:///c:/Project/2026/src/qx/portfolio/allocator.py)

- Inspect live/simulated position holdings and net sector deltas/gammas prior to trade recommendation.
- Veto or heavily penalize trades that exceed max sector concentration limits (e.g. $>25\%$ Tech exposure) or duplicate existing open leg risks.

---

### 5. Complete Trade Lifecycle Validation
Track trade progression from entry to final outcome for empirical performance auditing.

#### [MODIFY] [journal.py](file:///c:/Project/2026/src/qx/storage/journal.py)
#### [NEW] [lifecycle.py](file:///c:/Project/2026/src/qx/execution/lifecycle.py)

- Track full trade state machine transitions:
  `PROPOSED` → `PENDING_ENTRY` → `ACTIVE` → `PARTIAL_TARGET` → `STOPPED_OUT` / `TARGET_REACHED` / `EARLY_EXIT` / `EXPIRED`.
- Record exact slippage, timestamp duration, and realized R-multiple in SQLite journal DB.

---

### 6. Signal Score Calibration & Reliability Engine
Verify whether high signal quality scores translate into superior realized returns.

#### [NEW] [calibration.py](file:///c:/Project/2026/src/qx/signals/calibration.py)

- Aggregate historical trade outcomes into score buckets: `Tier 1 (80-100)`, `Tier 2 (60-79)`, `Tier 3 (0-59)`.
- Compute Brier Score, bucket win rates, and expected return monotonicity ($E[R | \text{Tier 1}] > E[R | \text{Tier 2}]$).
- Automatically adjust scoring weights if a signal factor loses predictive power.

---

### 7. Freshness & Latency Verification
Prevent execution on technically valid but operationally stale market signals.

#### [NEW] [freshness.py](file:///c:/Project/2026/src/qx/signals/freshness.py)
#### [MODIFY] [order_router.py](file:///c:/Project/2026/src/qx/execution/order_router.py)

- Check quote timestamp age against configurable max freshness thresholds (e.g., max 3 seconds for intraday scalps, 60 seconds for swing setups).
- Reject execution proposals if quote freshness or signal bar latency exceeds operational bounds (`publication_state: STALE_BLOCKED`).

---

## Verification Plan

### Automated Unit & Integration Tests
Run pytest across all signal quality, walk-forward, and real option-chain tests:
```bash
pytest tests/unit/test_phase2_hardening.py tests/unit/test_walk_forward_validation.py tests/unit/test_signal_quality.py -v
```

### Pre-Flight System Suite
Run repository-wide regression verification:
```bash
pytest tests/ -m "not slow"
```

### Manual & Telemetry Verification
- Run signal calibration analysis on sample historical data.
- Verify options chain data contracts in `/api/options-scanner/ideas`.
