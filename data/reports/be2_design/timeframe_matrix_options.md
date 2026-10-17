# BE2 Timeframe Matrix Options: Concrete Candidate Proposals

This document defines three concrete, actionable options for the multi-timeframe contract across the **DAY**, **SWING**, and **INVEST** horizons.

---

## OPTION A: Institutional Tri-Tier Matrix (Strict Confirmation)

### 1. Timeframe Tiers by Horizon

| Horizon | Execution TF (Trigger) | Setup TF (Pattern & Playbook) | HTF (Trend & Structure) | Macro Context |
| :--- | :--- | :--- | :--- | :--- |
| **DAY** | **1m** | **5m** | **15m** | Daily (1d) |
| **SWING** | **15m** | **1h** | **Daily (1d)** | Weekly (1w) |
| **INVEST** | **Daily (1d)** | **Weekly (1w)** | **Monthly (1M)** | Quarterly / Annual |

### 2. Tier Responsibilities
- **Execution TF**: Precision entry trigger, micro-invalidation, instantaneous VWAP/Delta test.
- **Setup TF**: Primary SMC structure (pivots, order blocks, FVG), playbook identification (ORB, Pullback, Liquidity Sweep), initial risk-reward calculation.
- **HTF**: Directional bias filter. Must be confirmed in the same direction or Neutral.
- **Macro**: Market regime baseline.

### 3. Conflict Handling
- If Setup TF is `BULLISH` and HTF is `BEARISH`: **BLOCKED** (`HTF_DIRECTIONAL_DISCORDANCE`).
- If Setup TF is `BEARISH` and HTF is `BULLISH`: **BLOCKED** (`HTF_DIRECTIONAL_DISCORDANCE`).
- If Setup TF is directional and HTF is `NEUTRAL`: Permitted to proceed to `ARMED` with warning code.

### 4. Incomplete HTF Candles
- Incomplete HTF candles are strictly excluded from HTF pivot and structure detection.
- HTF structure is evaluated exclusively on bars with $T_{\text{completion}} \le T_{\text{eval}}$.

### 5. Missing HTF Behavior
- **Fails Closed**: If HTF bar data is unavailable or stale beyond maximum lookback, setup state is forced to `BLOCKED` (`HTF_DATA_MISSING`).

### 6. Pipeline & Phase 3–10 Implications
- Requires running Phase 4 SMC twice (once on Setup TF, once on HTF).
- Direction Engine Factor #7 receives confirmed HTF structure with configured weight `0.10`.
- Playbook gate enforces HTF concordance check before transitioning from `WATCH` to `ARMED`.

---

## OPTION B: Dual-Timeframe Evidence Matrix (Weighted Soft Gate)

### 1. Timeframe Tiers by Horizon

| Horizon | Primary Setup / Execution TF | Contextual Higher Timeframe (HTF) | Macro Reference |
| :--- | :--- | :--- | :--- |
| **DAY** | **5m** | **1h** | Daily (1d) |
| **SWING** | **1h** | **Daily (1d)** | Weekly (1w) |
| **INVEST** | **Daily (1d)** | **Weekly (1w)** | Monthly (1M) |

### 2. Tier Responsibilities
- **Primary Setup / Execution TF**: Drives the entire canonical lifecycle (`WATCH` -> `ARMED` -> `TRIGGERED` -> `TRADEABLE`). All entry triggers, stops, targets, and playbook logic remain bound to this timeframe.
- **Contextual HTF**: Feeds directly into Factor #7 of the Direction Engine (`compute_higher_timeframe_factor`) with configured weight `0.10`.
- **Macro Reference**: Provides background regime and sector alignment scores.

### 3. Conflict Handling
- No hard veto at the playbook level.
- If Primary is `BULLISH` and HTF is `BEARISH`:
  - HTF Factor scores `-100.0` with `effective_weight = 0.10`.
  - Direction Score is penalized by up to 20 points in the weighted sum.
  - If other factors (Delta, Structure, VWAP) remain overwhelmingly bullish, Direction Score may still pass the playbook threshold (`>= 20.0`), allowing the trade.
  - If overall Direction Score falls below threshold, playbook stays in `WATCH` or `NO_SETUP`.

### 4. Incomplete HTF Candles
- Incomplete HTF candles are excluded from HTF structure calculations.
- Current intraday price on the 5m bar reflects real-time movement.

### 5. Missing HTF Behavior
- **Graceful Degradation**:
  - Missing HTF does NOT block the opportunity.
  - HTF Factor is marked `UNAVAILABLE`, `reliability = 0.0`.
  - Evidence Coverage drops from `1.00` (Complete) to `0.90` (Adequate).
  - Reason code `HTF_CONTEXT_UNAVAILABLE` is attached for full transparency.

### 6. Pipeline & Phase 3–10 Implications
- **Zero Breaking Changes to Existing Lifecycle**:
  - Lifecycle state machine remains untouched.
  - Perfectly matches the existing 7-factor Direction Engine mathematical formula.
  - Safest and lowest risk for automated regression.

---

## OPTION C: Asymmetric Horizon-Tailored Matrix

### 1. Timeframe Tiers by Horizon

| Horizon | Execution TF | Setup TF | HTF | Policy Profile |
| :--- | :--- | :--- | :--- | :--- |
| **DAY** | **5m** | **5m** | **15m** | **Soft Evidence (Model B)**: Rapid intraday moves allow counter-trend scalps if volume delta confirms. |
| **SWING** | **15m** | **1h** | **Daily (1d)** | **Concordance Required (Model A)**: Multi-day holding cannot fight Daily structural trend. |
| **INVEST** | **Daily (1d)** | **Daily (1d)** | **Weekly (1w)** | **Strict Veto (Model A)**: No long equity investments against weekly downtrends. |

### 2. Tier Responsibilities
- Tailored per trading style: Day trading prioritizes tactical responsiveness; Investing prioritizes strategic alignment.

### 3. Conflict Handling
- **DAY**: Weighted penalty in Direction Score (allows intraday counter-trend mean reversion).
- **SWING & INVEST**: Opposing HTF forces `BLOCKED` (`COUNTER_HTF_FORBIDDEN`).

### 4. Incomplete HTF Candles
- Universal rule: Incomplete bars are strictly excluded from structural pivots.

### 5. Missing HTF Behavior
- **DAY**: Missing HTF drops coverage to `0.90`; trading continues.
- **SWING & INVEST**: Missing HTF forces `BLOCKED` (fails closed).

### 6. Pipeline & Phase 3–10 Implications
- Introduces horizon-dependent policy branching in `src/qx/playbooks/` and `src/qx/pipeline/orchestrator.py`.
- Slightly higher testing matrix complexity, but highest fidelity to institutional trading desks.

---

## Comparison Matrix

| Dimension | Option A (Strict Tri-Tier) | Option B (Dual-TF Soft Gate) | Option C (Asymmetric Tailored) |
| :--- | :--- | :--- | :--- |
| **Architectural Disruption** | Moderate | Minimal (Native to core_v1) | Moderate to High |
| **False Rejection Rate** | High (Vetoes counter-trend plays) | Low (Evaluates full evidence) | Balanced by horizon |
| **Missing HTF Resilience** | Fails closed (`BLOCKED`) | Graceful degradation (`0.90` cov) | Fails closed on Swing/Invest |
| **Replay Complexity** | 3 synchronized bar streams | 2 synchronized bar streams | Variable (2 to 3 streams) |
| **Implementation Risk** | Medium | Lowest | Medium-High |
