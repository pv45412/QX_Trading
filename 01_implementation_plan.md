# Phase 3 Completion Pass — Financial Correctness Implementation Plan

This implementation plan outlines the architectural corrections, financial safety rules, and regression tests required for **Phase 3 Completion Pass** on the QX Platform.

The objective of this pass is to enforce 100% financial correctness and fail-closed security before any read-only live Schwab account connection.

---

## User Review Required

> [!IMPORTANT]
> **Strict ReadOnlyBrokerPortfolioProvider Interface**: `ReadOnlyPortfolioService` will require an explicit `ReadOnlyBrokerPortfolioProvider` interface (`get_account_snapshot()`, `get_positions()`, `get_open_orders()`). All synthetic `$500,000` equity fallbacks will be removed. If no verified broker snapshot exists, the system will fail closed (`publication_state: BLOCKED`, `executable: False`). The provider contains **zero** order placement, cancellation, modification, or funds transfer methods.

> [!CAUTION]
> **Option Contract Sizing & Proposal Correctness**: Option trade proposals must use the actual option `contract_symbol` (e.g. `NVDA_270917C120`), option bid/ask/mid price, expiration, strike, and 100x contract multiplier. Trade proposals will **never** use the underlying stock symbol and stock limit price. Long options must size risk from `premium * 100`, defined-risk spreads from `analytical_max_loss`. Sizing errors or missing stop loss will fail closed (`recommended_units: 0`).

---

## Architecture & Data Flow

```
   Schwab Read-Only API
            ↓
 ReadOnlyBrokerPortfolioProvider
            ↓
 Background Scheduled Polling Worker (~30s Thread-Safe Cache)
            ↓
  PortfolioSnapshot (Equity, Positions, 100x Multipliers, Greeks)
            ↓
   Dynamic Trade Sizing (Strategy Max Loss / Account Equity Risk Limit)
            ↓
 Portfolio Risk Context (Dynamic Exposure %, Duplicate Trade Filter)
            ↓
 Option Chain Verification (Provider, Timestamp, Freshness, Ask > 0)
            ↓
        Freshness Gate (Quote & Signal Timestamps)
            ↓
 VERIFIED + Executable Option Contract Proposal
```

---

## Proposed Changes

### 1. Read-Only Broker Portfolio Provider & No Synthetic Fallbacks

#### [MODIFY] [models.py](file:///c:/Project/2026/src/qx/portfolio/models.py)
#### [MODIFY] [read_only_service.py](file:///c:/Project/2026/src/qx/portfolio/read_only_service.py)

- Define `ReadOnlyBrokerPortfolioProvider` protocol:
  - `get_account_snapshot() -> Optional[AccountSnapshot]`
  - `get_positions() -> list[PortfolioPosition]`
  - `get_open_orders() -> list[dict[str, Any]]`
  - Zero execution/cancel/modify methods.
- Remove synthetic `$500,000` equity default values in `ReadOnlyPortfolioService`. If provider returns `None` or is uninitialized, set `freshness_state: STALE_BLOCKED` and fail closed.
- Implement thread-safe background scheduler refresh in `PortfolioCache` using `threading.Lock()`.

---

### 2. Schwab Greeks Parsing & Option Multiplier Math

#### [MODIFY] [options.py](file:///c:/Project/2026/src/qx/brokers/schwab/options.py)
#### [MODIFY] [greeks_risk.py](file:///c:/Project/2026/src/qx/portfolio/greeks_risk.py)

- Parse `delta`, `gamma`, `theta`, and `vega` from Schwab option chain payload in `_contract_from_payload()`.
- Use 100x multiplier for option position market value (`quantity * price * 100`) and net option Greeks (`quantity * greek * 100`) in `calculate_portfolio_greeks()`.

---

### 3. Option Proposal Construction & Contract Symbol Execution

#### [MODIFY] [pipeline.py](file:///c:/Project/2026/src/qx/execution/pipeline.py)
#### [MODIFY] [order_router.py](file:///c:/Project/2026/src/qx/execution/order_router.py)

- When an option strategy is selected, construct `OrderRequest` using:
  - `symbol = option_contract.contract_symbol` (e.g. `NVDA_270917C120`)
  - `limit_price = option_contract.mid`
  - `underlying_symbol = quote.symbol`
  - `strategy_type = "OPTION"`
- Prevent creating option proposals using underlying stock symbol and stock price.

---

### 4. Strategy Max Loss Position Sizing & Fail-Closed Sizing

#### [MODIFY] [position_sizer.py](file:///c:/Project/2026/src/qx/options_scanner/services/position_sizer.py)

- Long Option sizing: `max_risk = premium * 100`.
- Vertical Spread sizing: `max_risk = analytical_max_loss`.
- Remove entry == stop 5% risk fallback. If stop loss or max loss is invalid/undefined, return `recommended_units = 0` and mark `is_valid: False`.

---

### 5. Strengthened Option-Chain Verification & Dynamic Proposed Exposure

#### [MODIFY] [chains.py](file:///c:/Project/2026/src/qx/options/chains.py)
#### [MODIFY] [pipeline.py](file:///c:/Project/2026/src/qx/execution/pipeline.py)
#### [MODIFY] [veto_service.py](file:///c:/Project/2026/src/qx/options_scanner/services/veto_service.py)

- Add chain evidence metadata to `OptionContract` and chain snapshots (`provider`, `retrieved_at`, `chain_timestamp`, `evidence_source`).
- Replace hardcoded `proposed_addition_pct = 3.0` with dynamic calculation: `(capital_required / account_equity) * 100.0`.
- Refine duplicate risk: holding underlying stock is investment exposure, not automatically a duplicate option trade veto unless an active QX option trade in the same direction exists.

---

### 6. Comprehensive Regression Test Suite

#### [NEW] [test_phase3_financial_correctness.py](file:///c:/Project/2026/tests/unit/test_phase3_financial_correctness.py)

Add 13 explicit regression test cases:
1. Missing portfolio snapshot never produces a synthetic $500K account.
2. Stale or missing broker snapshot cannot become `VERIFIED`.
3. Option orders use actual `contract_symbol` and option mid price.
4. Long option position sizing uses `premium * 100` max loss.
5. Vertical spread sizing uses analytical max loss.
6. Option Greeks and market values use 100x contract multiplier.
7. Proposed sector concentration is calculated dynamically from actual trade size.
8. Holding underlying stock alone does not trigger duplicate option trade veto.
9. Schwab option chain parser populates delta, gamma, theta, and vega.
10. Sizing errors fail closed with zero units.
11. Portfolio cache thread-safety lock verification.
12. Dual timestamp freshness blocks stale signals.
13. End-to-end fail-closed pipeline verification.

---

## Verification Plan

### Automated Unit & Regression Tests
Run pytest on all hardening and financial correctness test suites:
```bash
pytest tests/unit/test_phase2_hardening.py tests/unit/test_phase3_signal_quality.py tests/unit/test_phase3_integration_pipeline.py tests/unit/test_phase3_financial_correctness.py -v
```

### Full Repository Regression Run
```bash
pytest tests/ -m "not slow"
```
