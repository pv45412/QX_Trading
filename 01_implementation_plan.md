# QX Phase 3 — Integration, Validation & Read-Only Portfolio Context Implementation Plan

This implementation plan outlines the architecture, security boundaries, score separation, and verification workflow for the **Phase 3 Integration Pass** on the QX Platform.

The focus of this pass is **pure pipeline integration and security hardening**—connecting existing Phase 3 components into one unified production pipeline and adding a lightweight, strictly read-only portfolio context layer.

---

## User Review Required

> [!IMPORTANT]
> **Strict Read-Only Security Boundary**: `ReadOnlyPortfolioService` will be strictly isolated from the execution engine (`OrderRouter`). The broker connector will contain zero methods for placing, modifying, canceling, or routing orders, or transferring funds. Permissions are enforced at both the API connector and service layer.

> [!NOTE]
> **Scoring Transparency & Veto Isolation**: Technical signal quality (`signal_quality_score`) will be kept separate from portfolio compatibility (`portfolio_fit_score`) and risk limits (`risk_score`). Portfolio vetoes will never be hidden inside the technical score and will emit explicit typed veto reasons (e.g. `PORTFOLIO_CONCENTRATION`, `ACCOUNT_RISK_LIMIT`).

> [!CAUTION]
> **Equity-Based Position Sizing**: Position sizing will be calculated strictly from `Account Equity * Max Risk Per Trade %` and the actual defined stop-loss dollar risk. Buying power alone will **never** be used to determine trade size.

---

## Architecture Topology

```
                  ┌─────────────────────┐
                  │  Real-Time Market   │
                  │       Data          │
                  └─────────┬───────────┘
                            ↓
                  Signal / Structure
                            ↓
                   Signal Validator
                            ↓
                     Trade Candidate
                            ↓
       ┌────────────────────┴──────────────────┐
       ↓                                       ↓
Verified Option Chain                 Read-Only Portfolio Cache (~30s)
       ↓                                       ↓
Option Validation                     Portfolio Risk Context
       └────────────────────┬──────────────────┘
                            ↓
                     Trade Scoring (Signal / Fit / Risk / Final)
                            ↓
                     Freshness Gate (Quote & Signal Timestamps)
                            ↓
                    Publication Gate
                            ↓
                  VERIFIED + executable?
                       ↓           ↓
                      NO          YES
                      ↓            ↓
                   Research     Order Proposal
```

---

## Proposed Changes

### 1. Read-Only Portfolio Context & Caching Layer

#### [MODIFY] [models.py](file:///c:/Project/2026/src/qx/portfolio/models.py)
#### [NEW] [read_only_service.py](file:///c:/Project/2026/src/qx/portfolio/read_only_service.py)

- Create `PortfolioSnapshot` containing:
  - `account_id_hash`, `as_of`, `source`, `freshness_state` (`FRESH`, `STALE_WARNED`, `STALE_BLOCKED`).
  - Account equity, cash/buying power, current positions, market values, cost basis, open orders, and option Greeks.
- Create `ReadOnlyPortfolioService` with cached polling (30s configurable refresh window: 15–60s).
- Ensure signal scanners read from cache and never trigger synchronous broker HTTP requests on scanner loops.

---

### 2. Portfolio Veto Reasons & Risk Context

#### [MODIFY] [models.py](file:///c:/Project/2026/src/qx/options_scanner/models.py)
#### [MODIFY] [veto_service.py](file:///c:/Project/2026/src/qx/options_scanner/services/veto_service.py)

- Add explicit portfolio veto reasons to `VetoReasonEnum`:
  - `PORTFOLIO_CONCENTRATION`, `SYMBOL_CONCENTRATION`, `SECTOR_CONCENTRATION`
  - `DUPLICATE_RISK`, `ACCOUNT_RISK_LIMIT`, `INSUFFICIENT_BUYING_POWER`
  - `GREEKS_UNAVAILABLE`, `PORTFOLIO_DATA_STALE`
- Evaluate single-symbol concentration, sector concentration (e.g. max 25%), net option delta exposure, and duplicate open trade risk.

---

### 3. Decoupled Trade Scoring & Account Equity Position Sizing

#### [NEW] [trade_scorer.py](file:///c:/Project/2026/src/qx/options_scanner/services/trade_scorer.py)
#### [NEW] [position_sizer.py](file:///c:/Project/2026/src/qx/options_scanner/services/position_sizer.py)

- Implement `TradeScoreBreakdown` preserving 4 distinct scores:
  - `signal_quality_score` (0–100, technical setup from `SignalValidator`).
  - `portfolio_fit_score` (0–100, sector/symbol concentration fit).
  - `risk_score` (0–100, account risk adherence).
  - `final_trade_score` (composite overall score).
- Implement `AccountEquityPositionSizer`:
  - `Max Trade Dollar Risk = Account Equity * Max Risk Per Trade %` (e.g., $500k equity * 0.50% = $2,500 max loss).
  - `Allowed Contracts / Shares = Max Trade Dollar Risk / Stop Loss Risk Per Contract`.

---

### 4. Market & Signal Freshness Gating

#### [MODIFY] [freshness.py](file:///c:/Project/2026/src/qx/signals/freshness.py)
#### [MODIFY] [order_router.py](file:///c:/Project/2026/src/qx/execution/order_router.py)

- Evaluate dual freshness thresholds: `quote_timestamp` age and `signal_timestamp` age.
- Warn at soft threshold; set `publication_state = BLOCKED` and `executable = False` once hard threshold is breached.

---

### 5. Production Pipeline Integrator & End-to-End Suite

#### [NEW] [pipeline.py](file:///c:/Project/2026/src/qx/execution/pipeline.py)
#### [NEW] [test_phase3_integration_pipeline.py](file:///c:/Project/2026/tests/unit/test_phase3_integration_pipeline.py)

- Build `Phase3PipelineIntegrator` wiring all steps end-to-end.
- Write regression suite testing both critical paths:
  1. **Successful Path**: Verified market quote + Signal Validation + Verified Option Chain + Cached Portfolio Snapshot + Portfolio Risk Check + Freshness Check → `VERIFIED` + `executable = True` proposal.
  2. **Fail-Closed Path**: Any stale quote, missing option chain, simulated data, or portfolio risk limit breach → `publication_state = BLOCKED` or `SIMULATED`, `executable = False`.

---

## Verification Plan

### Automated Regression Tests
Run pytest across Phase 2, Phase 3 unit tests, and the new integration pipeline suite:
```bash
pytest tests/unit/test_phase2_hardening.py tests/unit/test_phase3_signal_quality.py tests/unit/test_phase3_integration_pipeline.py -v
```

### Full Repository Regression Run
```bash
pytest tests/ -m "not slow"
```
