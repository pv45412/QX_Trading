# MD1 Market Driver Engine Design Proposal

**Status**: READY FOR HUMAN REVIEW  
**Task ID**: MD1  
**Milestone**: Architecture & Semantic Specification Synthesis  
**Orchestrator**: QX Orchestrator V2  
**Date**: 2026-09-17  

---

## 1. Executive Summary

This proposal presents the synthesized architectural, quantitative, causality, replay, and user-experience specifications for **MD1: Market Driver Engine Design**.

In accordance with QX Autonomous Delivery Governance:
- **No production engine code has been implemented prematurely.**
- Existing pipelines and suites remain 100% green (2,346 backend tests, 133 web tests passing).
- Phase 11 broker write execution remains strictly locked.
- Read-only specialist investigations are completed across 6 dedicated design reports in `data/reports/md1_design/`.
- Concrete semantic options are presented for human authorization prior to MD2 implementation.

The goal of the Market Driver Engine is to provide a deterministic, point-in-time causal explanation of **WHAT** is moving the market and individual symbols, answering operator conviction questions without duplicating or replacing:
- **Regime** (*environmental state: trend, volatility, gamma, session*)
- **Direction** (*vector: directional score $[-100, +100]$ and bias*)
- **Structure** (*geography: swing pivots, order blocks, fair value gaps, liquidity pools*)
- **Playbooks** (*tactics: setup pattern matching*)
- **Tradeability** (*feasibility: spread, liquidity, execution safety*)

---

## 2. Key Specialist Findings

1. **Architecture Lens**:
   - Market Driver must live as an **independent explanatory stage** in the pipeline, executing after Direction and Playbooks but before or in parallel with Opportunity publication.
   - It must be **strictly non-authoritative** over canonical lifecycle transitions (`WATCH`, `ARMED`, `TRIGGERED`, `TRADEABLE`).
   - The backend is the single source of truth; the frontend is strictly forbidden from inferring or calculating drivers.

2. **Quant / Microstructure Lens**:
   - Identified 11 canonical driver archetypes across 5 market forces:
     - *Index systemic flow*: `INDEX_RISK_ON`, `INDEX_RISK_OFF`
     - *Sector alpha / rotation*: `SECTOR_LEADERSHIP`, `SECTOR_LAG`
     - *Dealer positioning*: `GAMMA_PINNING`, `GAMMA_SQUEEZE`
     - *Microstructure aggression*: `DELTA_AGGRESSION`, `LIQUIDITY_ABSORPTION`
     - *Equilibrium & catalysts*: `VWAP_MEAN_REVERSION`, `MACRO_CATALYST`, `IDIOSYNCRATIC_FLOW`
   - Established a mathematical **Hysteresis Buffer** ($\Delta = 10.0$) to eliminate flip-flopping and cognitive fatigue.

3. **Data / Causality Lens**:
   - Strict point-in-time invariant: $T_{\text{event}} \le T_{\text{knowledge}} \le T_{\text{eval}}$. Zero future bar lookahead.
   - Hierarchical coverage status: `COMPLETE` (5/5 sources), `PARTIAL` (3–4 sources), `INSUFFICIENT` ($<3$ sources $\rightarrow$ fails closed to `UNAVAILABLE`), and `BLOCKED` (temporal corruption).

4. **Replay / Validation Lens**:
   - Formulated 8 core invariant tests (`INV-MD-01` through `INV-MD-08`).
   - Bit-for-bit parity guaranteed across Live, Shadow, and Historical Replay modes.
   - Session flip-rate target: $\le 4$ primary driver switches per 6.5-hour trading day.

5. **UX Projection Lens**:
   - 100% compliant with `data/reports/qx_product_design/market_driver_spec.md`.
   - Compact form for Today and Opportunities workspaces; Expanded interactive Bento panel for Trade and Research workspaces.

---

## 3. Concrete Semantic Options for Human Review

We present three distinct architectural options:

### Summary Comparison

| Dimension | Option A: Deterministic Hierarchical Priority Tree | Option B: Multi-Factor Continuous Decomposition (Recommended) | Option C: Hybrid Regime-Conditioned Structural Engine |
| :--- | :--- | :--- | :--- |
| **Model** | Ordered if-else decision ladder with discrete threshold cutoff gates. | Normalized multi-factor scoring with hysteresis-buffered rank selection. | Top-level branching determined by `MarketRegime`, followed by sub-tree factor matching. |
| **Primary Driver** | First rule in hierarchy whose conditions evaluate to `True`. | Candidate archetype with highest magnitude: $M_k = \|S_k\| \times R_k \ge 35.0$. | Constrained to archetype sub-tree corresponding to active `MarketRegime`. |
| **Secondary Drivers**| Subsequent rules in hierarchy meeting threshold (up to 2). | Second and third highest candidates meeting hurdle ($M \ge 20.0$). | Secondary factors within the regime-filtered sub-tree. |
| **Stability / Hysteresis**| Prone to thrashing at boundary edges (e.g. 49.9 vs 50.1). | **High**: Requires candidate to exceed incumbent by $\Delta \ge 10.0$ to replace. | Moderate: Vulnerable to transitions between `MarketRegime` states. |
| **Evidence Partitioning**| Hardcoded boolean checks per rule. | **Natural & Direct**: Matching sign $\rightarrow$ Confirming; Opposing sign $\rightarrow$ Conflicting. | Heuristic attribution from SMC structure and regime components. |
| **Coupling** | Low. | Low. | High (cascades regime engine classification shifts). |

---

## 4. Causality Constraints & Data Dependencies

1. **Temporal Boundaries**: All candidate inputs (bars, benchmark index, sector ETF, order flow delta, dealer gamma) must satisfy $T \le T_{\text{eval}}$.
2. **Completed Candle Requirement**: Multi-timeframe and benchmark candles must be confirmed closed (following BE2 completed candle contract).
3. **Fail-Closed Hurdle**: If fewer than 3 of the 5 evidence families are available, the engine emits `UNAVAILABLE` with reason code `INSUFFICIENT_EVIDENCE_COVERAGE`.
4. **Stale Data SLA**: Inputs exceeding freshness thresholds degrade reliability by 50% rather than causing silent failure.

---

## 5. UI Projection Summary

The frontend remains a purely passive renderer:
- **Today / Opportunities**: Compact card displaying Primary Driver, Strength badge, Persistence duration, Evidence count summary (e.g. `3 confirming / 1 conflicting`), and Coverage state.
- **Trade / Research**: Expanded interactive attribution card showing Primary Driver, Secondary Drivers, clickable Confirming / Conflicting chips with source stages, and full Coverage audit.
- **Zero Frontend Inference**: When backend serves `market_driver = null` or `status = "UNAVAILABLE"`, the frontend displays "Market driver unavailable".

---

## 6. Genuine Human Decisions Required

Before MD2 implementation can begin, human governance decisions are required on:

1. **Engine Architecture Selection**:
   - Approve **Option B** (Recommended: Continuous Multi-Factor Decomposition with Hysteresis), or choose Option A or Option C.
2. **Lifecycle Influence**:
   - Confirm that Market Driver remains **100% explanatory context** with **ZERO lifecycle veto or promotion authority**, OR specify any desired gating behavior.
3. **Coverage Threshold**:
   - Confirm the proposed 3-of-5 minimum evidence family requirement for `AVAILABLE` / `PARTIAL` status before failing closed to `UNAVAILABLE`.
4. **Hysteresis Sensitivity**:
   - Confirm the proposed $\Delta = 10.0$ hysteresis hurdle and maximum 4 flips/day target for operator cognitive stability.

---

## 7. Artifact Index

The comprehensive specialist investigation reports are located in `data/reports/md1_design/`:
1. [current_state_and_input_analysis.md](file:///c:/Project/2026/data/reports/md1_design/current_state_and_input_analysis.md)
2. [semantic_options.md](file:///c:/Project/2026/data/reports/md1_design/semantic_options.md)
3. [causality_and_provenance_contract.md](file:///c:/Project/2026/data/reports/md1_design/causality_and_provenance_contract.md)
4. [validation_plan.md](file:///c:/Project/2026/data/reports/md1_design/validation_plan.md)
5. [ui_projection.md](file:///c:/Project/2026/data/reports/md1_design/ui_projection.md)
6. [risk_analysis.md](file:///c:/Project/2026/data/reports/md1_design/risk_analysis.md)
