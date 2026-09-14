# Master QX Platform Remediation & Truth Layer Implementation Plan

Combine system architecture fixes (SQLite WAL mode, /ES basis spread, FVG lookahead bias, React schema alignment) with business-logic containment & truth layer enforcement (publication state control, canonical option pricing, signed portfolio P&L, analytical payoff bounds, GEX settlement filtering).

---

## User Review Required

> [!IMPORTANT]
> **Phase 0 Safety Containment**: Before modifying complex models, an explicit `publication_state` (`VERIFIED`, `RESEARCH_ONLY`, `SIMULATED`, `BLOCKED`) will be introduced. API endpoints `/api/spx-calendars` and `/api/options-scanner/ideas` will be flagged as `SIMULATED / DEMO` to prevent synthetic prototype data from being presented as verified actionable signals.

> [!NOTE]
> All trade construction, risk sizing, portfolio P&L, payoff metrics, and GEX calculations will be upgraded to use canonical real-market option chain evidence and analytical topology classification.

---

## Combined Master Execution Blueprint

```
Stage 0: Safety Containment & SQLite WAL Mode
  ├── 0.1 Enable SQLite WAL mode, busy_timeout=10000, synchronous=NORMAL in sqlite.py
  ├── 0.2 Add publication_state control (VERIFIED, RESEARCH_ONLY, SIMULATED, BLOCKED)
  └── 0.3 Relabel /api/spx-calendars & /api/options-scanner/ideas as SIMULATED / DEMO

Stage 1: Market Data Basis, Options Truth & Structure Lookahead
  ├── 1.1 Dynamic /ES to SPX cash basis correction (basis = price_es - price_spx)
  ├── 1.2 Restrict FVG & SMC pattern detection strictly to completed candles (t-1, t-2, t-3)
  └── 1.3 Implement strategy-specific TradeConstructors with leg-level liquidity & multi-leg event risk

Stage 2: Risk Engine, Signed Portfolio P&L & Position Advisor Consolidation
  ├── 2.1 Fix signed short position P&L in allocator.py; remove >10 contract multiplier bug
  └── 2.2 Expand risk_service.py to enforce portfolio open risk, sector concentration & buying power

Stage 3: Analytics Semantics, GEX Settlement & Payoff Topology
  ├── 3.1 Separate AM-settled monthly (SET) from PM-settled weekly/0DTE open interest in gex.py
  ├── 3.2 Replace default +-20% grid sampling with analytical payoff topology classification
  └── 3.3 Declare scope (DAILY_MACRO, PREMARKET, INTRADAY_VERIFIED) on all dashboard metrics

Stage 4: React Client Contract Alignment & Out-of-Sample Calibration
  ├── 4.1 Align JSON payloads in data_contracts.py with React client & add null-coalescing fallbacks
  └── 4.2 Calibrate setup scores and win probabilities on historical trade telemetry
```

---

## Component Impact & Files Breakdown

### [MODIFY] [`src/qx/storage/sqlite.py`](file:///c:/Project/2026/src/qx/storage/sqlite.py)
- Task 0.1: Add `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=10000;`, `PRAGMA synchronous=NORMAL;`.

### [NEW] [`src/qx/models/publication.py`](file:///c:/Project/2026/src/qx/models/publication.py)
- Task 0.2: Define `PublicationState` enum (`VERIFIED`, `RESEARCH_ONLY`, `SIMULATED`, `BLOCKED`) and metadata wrappers.

### [MODIFY] [`src/qx/interfaces/web.py`](file:///c:/Project/2026/src/qx/interfaces/web.py)
- Task 0.3: Relabel `/api/spx-calendars` and `/api/options-scanner/ideas` as `SIMULATED`, update `session_label` to `RTH LIVE` when cash market opens, and add publication state guards.

### [MODIFY] [`src/qx/market/futures_evidence.py`](file:///c:/Project/2026/src/qx/market/futures_evidence.py) & [`src/qx/execution/order_router.py`](file:///c:/Project/2026/src/qx/execution/order_router.py)
- Task 1.1: Compute live basis spread `basis = price_es - price_spx` and normalize `/ES` technical triggers into SPX cash equivalents.

### [MODIFY] [`src/qx/structure/fvg.py`](file:///c:/Project/2026/src/qx/structure/fvg.py) & [`src/qx/structure/engine.py`](file:///c:/Project/2026/src/qx/structure/engine.py)
- Task 1.2: Restrict FVG and BOS/CHoCH detection to historical completed bars ($t-1, t-2, t-3$) to eliminate lookahead bias.

### [MODIFY] [`src/qx/options_scanner/services/trade_constructor.py`](file:///c:/Project/2026/src/qx/options_scanner/services/trade_constructor.py)
- Task 1.3: Strategy-specific constructors, same-expiration verticals, leg-level liquidity rechecks, and multi-leg event window evaluation.

### [MODIFY] [`src/qx/portfolio/allocator.py`](file:///c:/Project/2026/src/qx/portfolio/allocator.py) & [`src/qx/models/position_advisor.py`](file:///c:/Project/2026/src/qx/models/position_advisor.py)
- Task 2.1: Fix signed short position P&L calculations; remove `quantity > 10` option multiplier bug; consolidate into `positions/health.py`.

### [MODIFY] [`src/qx/options/gex.py`](file:///c:/Project/2026/src/qx/options/gex.py)
- Task 3.1: Separate AM-settled monthly (SET) from PM-settled weekly/0DTE options; reframe GEX as an OI-based proxy.

### [MODIFY] [`src/qx/strategies/payoff/curve_calculator.py`](file:///c:/Project/2026/src/qx/strategies/payoff/curve_calculator.py)
- Task 3.2: Analytical payoff topology classification (bounded, unlimited upside, unlimited downside).

### [MODIFY] [`src/qx/market/data_contracts.py`](file:///c:/Project/2026/src/qx/market/data_contracts.py) & [`web/src/SPXFuturesWorkspace.jsx`](file:///c:/Project/2026/web/src/SPXFuturesWorkspace.jsx)
- Task 4.1: Synchronize Pydantic backend models with React client props and add null-coalescing fallbacks.

---

## Verification & Pre-Flight Protocol

1. **Stage 0 Test Verification**: `pytest tests/unit/test_storage.py` and `pytest tests/unit/test_web_api.py`.
2. **Stage 1 Test Verification**: `pytest tests/unit/test_structure_engine.py` and `pytest tests/unit/test_options_scanner_service.py`.
3. **Stage 2 Test Verification**: `pytest tests/unit/test_portfolio_engine.py` and `pytest tests/unit/test_position_advisor.py`.
4. **Stage 3 Test Verification**: `pytest tests/unit/test_spx_calendar_engine.py` and `pytest tests/unit/test_strategy_payoff_engine.py`.
5. **Stage 4 System Verification**: `python -m qx.tools.run_preflight_checks`.
