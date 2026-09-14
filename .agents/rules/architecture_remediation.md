# QX Platform Unified Master Architecture & Business-Logic Remediation Plan

## Objective
Harmonize architectural system fixes (SQLite concurrency, /ES basis spread, FVG lookahead bias, React schema contracts) with business-logic truth enforcement (publication state control, canonical option pricing, signed portfolio P&L, analytical payoff bounds, GEX settlement filtering).

---

## Unified Execution Roadmap

### Stage 0: Safety Containment & Infrastructure Hardening
- **0.1 SQLite Concurrency & WAL Mode**:
  - **Files**: `src/qx/storage/sqlite.py`, `src/qx/storage/pipeline.py`
  - Set `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=10000;`, `PRAGMA synchronous=NORMAL;` on all database connections.
- **0.2 Universal Publication State Control**:
  - **Files**: `src/qx/models/publication.py`, `src/qx/interfaces/web.py`
  - Introduce explicit `publication_state` (`VERIFIED`, `RESEARCH_ONLY`, `SIMULATED`, `BLOCKED`). Enforce a UI/API kill-switch blocking execution controls when state $\neq$ `VERIFIED`.
- **0.3 Deceptive Metrics Relabeling**:
  - **Files**: `src/qx/options/calendar/generator.py`, `src/qx/options/calendar/term_structure.py`, `src/qx/interfaces/web.py`
  - Relabel `/api/spx-calendars` and `/api/options-scanner/ideas` as `SIMULATED / DEMO`.
  - Fix term structure nomenclature inversion (`front_iv > back_iv` $\rightarrow$ `FRONT IV RICH`).
  - Rename "Max Profit" to "EST. PEAK P/L AT SHORT EXPIRY", "Breakeven Range" to "MODEL PROFIT RANGE AT SHORT EXPIRY", and remove uncalibrated win rate percentages (`85.4%`).

### Stage 1: Market Data Basis, Options Truth & Structure Lookahead
- **1.1 /ES Futures to SPX Cash Basis Correction**:
  - **Files**: `src/qx/market/futures_evidence.py`, `src/qx/execution/order_router.py`, `src/qx/execution/bracket_manager.py`
  - Compute live dynamic basis: `basis = price_es - price_spx`. Normalize `/ES` momentum triggers into SPX cash equivalents before strike selection.
- **1.2 Eliminate SMC / FVG Lookahead Bias**:
  - **Files**: `src/qx/structure/fvg.py`, `src/qx/structure/engine.py`, `src/qx/backtesting/engine.py`
  - Restrict Fair Value Gap (FVG) and BOS/CHoCH calculations strictly to completed historical candles ($t-1, t-2, t-3$). Fire live signals only on candle close confirmation.
- **1.3 Canonical Option Chain & Trade Constructors**:
  - **Files**: `src/qx/options_scanner/services/trade_constructor.py`, `src/qx/options_scanner/services/veto_service.py`
  - Create strategy-specific constructors (Verticals, Calendars, PMCC, Wheel). Enforce same-expiration for verticals.
  - Recheck leg-level liquidity (OI, volume, bid-ask spread) on selected strikes.
  - Evaluate multi-leg event risk over the entire interval between short and long expirations.

### Stage 2: Risk Engine, Signed Portfolio P&L & Position Advisor Consolidation
- **2.1 Signed Portfolio P&L Correction**:
  - **Files**: `src/qx/portfolio/allocator.py`, `src/qx/models/position_advisor.py`, `src/qx/positions/health.py`
  - Separate long market value, short liabilities, and signed cost basis. Ensure short position profits scale correctly when price drops.
  - Remove `quantity > 10` multiplier bug in `position_advisor.py` and consolidate position lifecycle logic into `positions/health.py`.
- **2.2 Portfolio-Level Risk Budget & Concentration**:
  - **Files**: `src/qx/options_scanner/services/risk_service.py`
  - Expand trade sizing to enforce portfolio open risk, delta/vega exposure, sector concentration, buying power, and assignment limits.

### Stage 3: Analytics Semantics, GEX Settlement & Payoff Topology
- **3.1 GEX AM vs PM Settlement & Zero-Gamma Solver**:
  - **Files**: `src/qx/options/gex.py`
  - Filter AM-settled monthly (SET) from PM-settled weekly/0DTE open interest. Reframe GEX as an OI-based proxy under explicit sign assumptions.
- **3.2 Analytical Payoff Topology**:
  - **Files**: `src/qx/strategies/payoff/curve_calculator.py`, `src/qx/strategies/payoff/metrics_calculator.py`
  - Classify payoff bounds analytically (bounded, unlimited upside, unlimited downside). Use price grid sampling only for chart visualization.
- **3.3 Explicit Scope Declaration & Volatility Strategy Fit**:
  - **Files**: `src/qx/market/spx_dashboard.py`, `src/qx/options_scanner/services/volatility_service.py`
  - Tag all dashboard state with scope (`DAILY_MACRO`, `PREMARKET`, `INTRADAY_VERIFIED`). Separate volatility state (CHEAP / FAIR / RICH) from strategy fit (long vs short premium).

### Stage 4: React Client Contract Alignment & Out-of-Sample Calibration
- **4.1 React Client Schema Alignment & Null-Coalescing**:
  - **Files**: `src/qx/market/data_contracts.py`, `web/src/data-utils.js`, `web/src/SPXFuturesWorkspace.jsx`
  - Align Python JSON contracts with React components. Add null-coalescing fallbacks for `gex_data`, `put_wall`, `call_wall`, and `gamma_flip`.
- **4.2 Score Calibration & Telemetry**:
  - **Files**: `src/qx/telemetry/telemetry_service.py`
  - Calibrate setup scores and win probability metrics against historical trade telemetry before releasing probability claims to the UI.
