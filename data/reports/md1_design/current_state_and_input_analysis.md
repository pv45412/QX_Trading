# MD1 Current State and Input Analysis

**Task**: MD1 Market Driver Engine Design  
**Authoritative Role**: Architecture & Quant Systems Specialist  
**Status**: DESIGN ARTIFACT (Read-Only Investigation)  

---

## 1. Context & Motivation

The QX platform provides comprehensive multi-stage evaluation of trading opportunities:
1. **SMC Structure Engine**: Identifies swing pivots, market structure breaks (BOS), changes of character (CHoCH), order blocks, and fair value gaps. (*Where are key levels and institutional liquidity?*)
2. **Market Regime Engine**: Classifies Trend (`TREND_UP`, `TREND_DOWN`, `RANGE`), Volatility (`COMPRESSED`, `NORMAL`, `EXPANDING`), Gamma (`POSITIVE_GAMMA`, `NEGATIVE_GAMMA`), and Session (`OPENING`, `TREND_SESSION`, `BALANCED`, `LATE_SESSION`). (*What environmental state is the market in?*)
3. **Direction Engine**: Aggregates 8 distinct factors into a normalized score $[-100, +100]$ and direction bias. (*Which way is the price tilted?*)
4. **Playbook Engine**: Detects setup patterns (Trend Continuation, Range Expansion, Failed Breakout, Liquidity Sweep). (*What tactical playbook matches?*)
5. **Entry Trigger Engine**: Validates micro-structure confirmation (candle closes, sweeps). (*Is the entry triggered right now?*)
6. **Tradeability Engine**: Validates spread, liquidity, ATR, and session gates. (*Can we safely execute right now?*)
7. **Options Expression & Portfolio Risk**: Computes strikes/Greeks and position sizing. (*How do we express and size the risk?*)

### The Missing Causal Link
Despite this depth, an operator observing an opportunity has no unified, deterministic answer to the fundamental question:
> **"WHAT specific institutional force is actively driving price movement right now?"**

Currently, the web frontend and API display:
```javascript
marketDriver: 'UNAVAILABLE'
```
As mandated by `data/reports/qx_product_design/market_driver_spec.md`, the frontend is strictly forbidden from inferring this information from regime, direction, news, or price.

---

## 2. Orthogonality & Non-Duplication Matrix

To prevent architectural bleed or circular dependencies, the Market Driver must be strictly orthogonal to existing stages:

| Dimension | Existing Stage | Market Driver Role | Clear Boundary |
| :--- | :--- | :--- | :--- |
| **Environmental State** | `MarketRegime` | Consumes regime as contextual state; does not re-classify trend/volatility. | Regime says *how* the market is behaving (e.g. expanding vol); Driver says *what force is driving it* (e.g. index de-grossing). |
| **Directional Bias** | `DirectionEngine` | Consumes directional factor components; does not emit Buy/Sell scores. | Direction outputs a scalar score $[-100, +100]$; Driver provides qualitative and structural causal attribution. |
| **Geometric Levels** | `smc_suite` | Consumes liquidity sweeps and breaks as evidence tokens. | Structure identifies price patterns; Driver explains if the move is local liquidity absorption vs macro index drag. |
| **Tactical Setups** | `PlaybookEngine` | Evaluates independently; Driver does NOT veto or promote playbooks. | Playbooks define trade entries; Driver provides explanatory conviction to the operator. |
| **Execution Feasibility**| `Tradeability` | Independent of spread/slippage gates. | Tradeability decides if execution is safe; Driver explains the macro/micro drivers behind the opportunity. |

---

## 3. Candidate Input Feeds & Feature Audit

An audit of existing feeds in `QXEvaluationContext` and external feeds reveals the following candidate inputs:

### Category A: Broad Index & Market Structure (Available)
- **Input**: Benchmark index bars (`SPY`, `QQQ`, `IWM`, `/ES`, `/NQ`).
- **Available Metrics**:
  - Index SMC structure (BOS, CHoCH, Swing status).
  - Index VWAP distance and slope (`ctx.vwap`, `ctx.vwap_slope`).
  - Index EMA trend alignment (`fast_ema`, `medium_ema`, `slow_ema`, slopes).
- **Driver Relevance**: High. Differentiates broad market systemic movement from idiosyncratic single-stock alpha.

### Category B: Breadth & Cross-Asset Participation (Partially Available / In Progress)
- **Input**: Advance/Decline ratio, % stocks above 20d/50d SMA, Tick index.
- **Available Metrics**: Currently accessible via `market_alignment_score` in `QXEvaluationContext`.
- **Driver Relevance**: Moderate/High. High breadth with index rally indicates broad institutional accumulation ("Broad Risk-On / Index Buying"); narrow breadth indicates megacap concentration.

### Category C: Sector Relative Strength & Divergence (Available)
- **Input**: Sector ETF performance (`XLK`, `XLF`, `XLE`, `XLV`, etc.) relative to SPY.
- **Available Metrics**: `ctx.relative_strength_score`, `ctx.sector_rs_age_seconds`.
- **Driver Relevance**: High. Detects sector rotation (e.g. Tech divergence vs defensive bid).

### Category D: Microstructure & Order Flow Delta (Available)
- **Input**: Aggressor trade delta, cumulative volume delta (CVD).
- **Available Metrics**: `ctx.delta_value`, `ctx.delta_provenance`, `ctx.delta_age_seconds`.
- **Driver Relevance**: High. Distinguishes aggressive market-order lifting/hitting from passive limit-order absorption.

### Category E: Options Dealer Gamma & Volatility (Available)
- **Input**: Net Gamma Exposure (GEX), Spot vs Gamma Flip, Realized ATR percentile.
- **Available Metrics**: `ctx.gex_data`, `ctx.gamma_value`, `ctx.gamma_provenance`, `ctx.atr`.
- **Driver Relevance**: High. Distinguishes gamma-pinned mean-reverting regimes from negative gamma short-gamma acceleration squeezes.

### Category F: Higher-Timeframe & Session Context (Available - BE2 Complete)
- **Input**: Synchronized completed HTF bars (`1h`, `Daily`, `Weekly`) via `evaluate_htf_structure`.
- **Available Metrics**: `ctx.htf_structure_state`, `ctx.htf_age_bars`, session regime (`OPENING`, `TREND_SESSION`, `BALANCED`, `LATE_SESSION`).
- **Driver Relevance**: High. Explains whether intraday moves are aligned with macro multi-week expansion or counter-trend liquidity re-tests.

### Category G: Macroeconomic & Event Catalysts (Source-Backed Only)
- **Input**: Economic calendar flags (FOMC, CPI, NFP) and corporate earnings.
- **Rule**: Must be source-backed with explicit event timestamps; heuristic guessing is strictly prohibited.

---

## 4. Architectural Summary

All required input categories (A through F) are already represented in `QXEvaluationContext` or accessible through verified deterministic pipeline engines. MD1 does not require speculative new vendor dependencies.
