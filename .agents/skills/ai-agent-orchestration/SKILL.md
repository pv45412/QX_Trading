---
name: ai-agent-orchestration
description: >-
  Standard execution protocol for multi-agent coordination on the QX Platform:
  Defines specialized subagent roles (Quant Engine, Market Structure, Options Risk, UI QA)
  and handoff validation protocols.
---

# Multi-Agent Orchestration Protocol

This skill governs the roles, handoff protocols, and output validation boundaries for multi-agent tasks on the QX Platform.

## 1. Agent Role Specializations

### Quantitative Analytics Agent
- **Responsibilities**: Compute relative strength metrics, ETF quadrant rankings, 5d/20d/60d RS alignment, stock movers, and intraday bar statistics.
- **Rules**: Must use cached market data providers (`_read_cached_bars`) or live feeds; never inject dummy synthetic values.

### Market Structure Agent
- **Responsibilities**: Analyze swing high/low pivots, SPX 15m Opening Range Breakouts (ORB), VWAP upper/lower bounds, and GEX gamma flip levels.
- **Rules**: Validate price touch tolerance and volume contraction ratios before signaling breakouts.

### Options Risk Specialist Agent
- **Responsibilities**: Calculate Black-Scholes Greeks, IV/RV volatility edge, option chain spreads, and dynamic position sizers.
- **Rules**: Enforce 100x contract multiplier math (`premium * 100`) and standard option contract symbol formatting (`SYMBOL_YYMMDDC/PPRICE`).

### Frontend QA Agent
- **Responsibilities**: Inspect React workspace components, check template formatting safety, enforce ErrorBoundary isolation, and verify URL router state.
- **Rules**: All template numerical calls must wrap with `(Number(val) || 0).toFixed(...)`.

---

## 2. Handoff & Verification Protocol

1. **Pre-Task Verification**: Execute preflight checker `.venv/Scripts/python.exe -m qx.tools.run_preflight_checks` before architectural changes.
2. **Data Model Integrity**: Ensure Pydantic models in Python mirror TypeScript interfaces in `web/src/types/`.
3. **Fail-Closed State**: If broker or live quote data is unreachable, publish `publication_state: BLOCKED` and set `is_read_only: true`.
