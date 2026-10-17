# BE2 Multi-Timeframe Context Proposal

**Status**: READY FOR HUMAN REVIEW  
**Task ID**: BE2  
**Milestone**: Design & Semantic Analysis Synthesis  
**Orchestrator**: QX Orchestrator V2  

---

## 1. Executive Summary

This proposal presents the synthesized architectural, quantitative, causality, validation, and user-experience findings for **BE2: Multi-Timeframe Context Contract**.

In accordance with QX Autonomous Delivery Governance:
- **No trading semantics have been implemented prematurely.**
- Single-timeframe canonical pipelines remain green (2,331 passing tests).
- All findings are documented across 7 specialized reports in `data/reports/be2_design/`.
- Three concrete, actionable decision options are submitted for human authorization.

---

## 2. Key Specialist Findings

1. **Architecture Agent**:
   - The pipeline currently accepts a single `ctx.timeframe` and single `ctx.bars` DataFrame.
   - However, **Direction Engine Factor #7 (`higher_timeframe`) is ALREADY implemented** with `configured_weight = 0.10` and `provenance = "CONFIRMED_HTF_SMC"`.
   - In production, it currently remains `UNAVAILABLE` because `QXEvaluationContext` defaults `htf_structure_state = "UNKNOWN"`.
   - **Safest Path**: Connect a point-in-time verified HTF SMC evaluation to populate this existing Factor #7 hook.

2. **Quant / Market Structure Agent**:
   - Defined functional hierarchy: Execution (1m/5m) $\rightarrow$ Setup (5m/1h/1d) $\rightarrow$ HTF (15m/1d/1w) $\rightarrow$ Macro (1d/1w/1M).
   - Examined trade-offs between hard structural vetoes (high win-rate, low frequency) versus soft evidence weighting (balanced capture, accommodates mean-reversion).

3. **Data / Causality Agent**:
   - Defined the strict point-in-time rule: $T_{\text{completion}} = T_{\text{start}} + \Delta_{\text{timeframe}} \le T_{\text{eval}}$.
   - **Incomplete HTF bars must NEVER be used for pivot detection or SMC confirmation.**
   - Defined fail-closed behavior for missing or stale higher timeframe feeds.

4. **Replay / Validation Agent**:
   - Designed 4 verification suites: causality/lookahead prevention, timeframe alignment resilience, replay/live parity, and persistence parity.
   - Replay engine must support multi-timeframe synchronized bar stepping.

5. **UX Agent**:
   - Confirmed no UI redesign is required.
   - Existing Opportunity cards and Trade metrics panels will absorb secondary timeframe indicators and Factor #7 breakdowns additively.

---

## 3. Human Decisions Required: Concrete Options

We present three concrete options for human approval. No option is pre-selected.

### Option Comparison Summary

| Metric / Dimension | Option A: Institutional Tri-Tier Matrix (Strict Confirmation) | Option B: Dual-Timeframe Evidence Matrix (Weighted Soft Gate) | Option C: Asymmetric Horizon-Tailored Matrix |
| :--- | :--- | :--- | :--- |
| **Timeframe Pairs (DAY)** | Setup: 5m · HTF: 15m · Exec: 1m | Setup: 5m · HTF: 1h | Setup: 5m · HTF: 15m (Soft) |
| **Timeframe Pairs (SWING)** | Setup: 1h · HTF: Daily · Exec: 15m | Setup: 1h · HTF: Daily | Setup: 1h · HTF: Daily (Strict) |
| **Timeframe Pairs (INVEST)**| Setup: Daily · HTF: Weekly · Exec: Daily | Setup: Daily · HTF: Weekly | Setup: Daily · HTF: Monthly (Strict) |
| **Conflict Behavior** | **Hard Veto**: Opposing HTF sets `BLOCKED` | **Soft Gate**: Penalizes Factor #7; allows trade if total score $\ge$ threshold | **Hybrid**: Soft on DAY, Strict Veto on SWING and INVEST |
| **Missing HTF Action** | Fails closed to `BLOCKED` | Degrades coverage to `0.90` (`ADEQUATE`); remains tradeable | Degrades on DAY; Fails closed on SWING/INVEST |
| **Impact on Core V1** | Alters Playbook gating logic | 100% compliant with existing Direction Engine Factor #7 | Adds horizon-conditional branching in playbooks |

---

## 4. Proposed Implementation Steps (Post-Approval)

Upon human authorization of one of the options above:
1. **Scaffold Multi-Timeframe Data Models**: Extend `QXEvaluationContext` to accept optional secondary bars or pre-computed HTF structure snapshots.
2. **Implement Point-in-Time HTF Filter**: Enforce candle close boundary ($T_{\text{completion}} \le T_{\text{eval}}$) to prevent future bar lookahead.
3. **Connect HTF Structure to Factor #7**: Evaluate HTF SMC structure and feed confirmed state into `compute_higher_timeframe_factor`.
4. **Enforce Approved Gate / Veto Rule**: Apply either Option A (playbook gate), Option B (evidence score penalty), or Option C (horizon-branching).
5. **Run Replay & Validation Suites**: Verify zero lookahead leakage and parity across live and replay adapters.

---

## 5. Artifact Index

The complete design investigation reports are available in `data/reports/be2_design/`:
1. [current_state_analysis.md](file:///c:/Project/2026/data/reports/be2_design/current_state_analysis.md)
2. [semantic_options.md](file:///c:/Project/2026/data/reports/be2_design/semantic_options.md)
3. [causality_contract.md](file:///c:/Project/2026/data/reports/be2_design/causality_contract.md)
4. [timeframe_matrix_options.md](file:///c:/Project/2026/data/reports/be2_design/timeframe_matrix_options.md)
5. [validation_plan.md](file:///c:/Project/2026/data/reports/be2_design/validation_plan.md)
6. [ui_projection.md](file:///c:/Project/2026/data/reports/be2_design/ui_projection.md)
7. [risk_analysis.md](file:///c:/Project/2026/data/reports/be2_design/risk_analysis.md)
