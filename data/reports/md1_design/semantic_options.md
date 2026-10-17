# MD1 Semantic Design Options

**Task**: MD1 Market Driver Engine Design  
**Authoritative Role**: Quant / Market Microstructure & Architecture Specialist  
**Status**: DESIGN ARTIFACT (Read-Only Investigation)  

---

## 1. Universal Driver Taxonomy

All options share the same standardized, human-readable institutional driver taxonomy. The engine maps quantitative inputs to this canonical vocabulary:

| Driver ID | Canonical Label | Direction | Primary Trigger Mechanism |
| :--- | :--- | :--- | :--- |
| `INDEX_RISK_ON` | Broad risk-on / index buying | BULLISH | Benchmark index (SPY/QQQ) trend alignment, positive breadth, and market alignment score $\ge +50.0$. |
| `INDEX_RISK_OFF` | Broad risk-off / index selling | BEARISH | Benchmark index trend alignment, negative breadth, and market alignment score $\le -50.0$. |
| `SECTOR_LEADERSHIP` | Sector outperformance / rotation | BULLISH | Sector relative strength $\ge +40.0$ while broad index is neutral or diverging. |
| `SECTOR_LAG` | Sector weakness / rotation outflow | BEARISH | Sector relative strength $\le -40.0$ while broad index is neutral or diverging. |
| `GAMMA_PINNING` | Dealer gamma pinning / compression | NEUTRAL | High positive GEX, spot near major strike wall, volatility compression ($ATR < 30$th percentile). |
| `GAMMA_SQUEEZE` | Negative gamma acceleration / squeeze | BULLISH/BEARISH | Spot in negative gamma territory with expanding ATR and directional order flow delta. |
| `DELTA_AGGRESSION` | Aggressive order flow imbalance | BULLISH/BEARISH | Buyer or seller trade aggressor delta exceeds $\pm 60.0$ with high trade delta reliability. |
| `LIQUIDITY_ABSORPTION` | Passive liquidity absorption | REVERSAL | Price sweeps key swing high/low or order block with opposing delta absorption. |
| `VWAP_MEAN_REVERSION` | Mean reversion to volume-weighted price | NEUTRAL/REVERSAL | Price deviation $> 2.0$ ATR from VWAP with declining momentum in balanced session. |
| `MACRO_CATALYST` | Scheduled macroeconomic event / news | MIXED | Verified event window (CPI, FOMC, NFP, Earnings) within $\pm 15$ minutes of announcement. |
| `IDIOSYNCRATIC_FLOW` | Uncorrelated symbol-specific flow | MIXED | Symbol moves independently of index, sector, and gamma; no single macro factor dominates. |

---

## 2. Option Comparison Matrix

| Architectural Dimension | Option A: Deterministic Hierarchical Priority Tree | Option B: Multi-Factor Weighted Continuous Decomposition (Recommended) | Option C: Hybrid Regime-Conditioned Structural Engine |
| :--- | :--- | :--- | :--- |
| **Classification Model** | Strict sequential decision tree with discrete threshold cutoff gates. | Continuous multi-factor activation scoring with hysteresis-buffered rank selection. | Top-level branching determined by `MarketRegime`, followed by local factor evaluation. |
| **Primary Driver Selection** | First rule in hierarchy whose conditions evaluate to `True`. | Highest continuous magnitude factor exceeding activation hurdle ($M \ge 35.0$). | Constrained to archetype sub-tree corresponding to active `MarketRegime`. |
| **Secondary Drivers** | Subsequent rules in hierarchy meeting threshold (up to 2). | Second and third highest factors exceeding secondary hurdle ($M \ge 20.0$). | Unused factors within the regime-filtered sub-tree. |
| **Driver Strength** | Discrete rule mappings (e.g. Delta $> 70 \rightarrow$ STRONG). | Continuous mapping: `WEAK` ($[35, 55)$), `MODERATE` ($[55, 75)$), `STRONG` ($\ge 75$). | Discrete step function based on regime confluence. |
| **Persistence Tracking** | Bar-count since primary driver ID changed. | Time and bar duration with hysteresis buffer ($\Delta \ge 10.0$ to replace incumbent). | Tied to regime duration and structural bar age. |
| **Confirming / Conflicting Evidence** | Hardcoded boolean checks per driver rule. | Direct mathematical sign alignment with primary driver's directional vector. | Heuristic attribution from SMC structure and regime components. |
| **Thrashing Risk** | High at boundary edges (e.g. index score 49.9 vs 50.1). | **Extremely Low** (dampened by hysteresis and continuous weighting). | Moderate (vulnerable when `MarketRegime` transitions). |
| **Coupling to Other Engines**| Low (reads raw inputs directly). | Low (reads raw inputs & factor reliabilities). | **High** (heavily dependent on `MarketRegime` stability). |

---

## 3. Detailed Architectural Specifications

### Option A: Deterministic Hierarchical Priority Tree
- **Logic**:
  1. If `macro_event_active` $\rightarrow$ `MACRO_CATALYST`
  2. Else if `abs(gamma_value) > gamma_threshold` and `volatility == EXPANDING` $\rightarrow$ `GAMMA_SQUEEZE`
  3. Else if `abs(market_alignment_score) >= 50.0` $\rightarrow$ `INDEX_RISK_ON` / `INDEX_RISK_OFF`
  4. Else if `abs(relative_strength_score) >= 40.0` $\rightarrow$ `SECTOR_LEADERSHIP` / `SECTOR_LAG`
  5. Else if `abs(delta_value) >= 60.0` and `delta_reliability >= 0.75` $\rightarrow$ `DELTA_AGGRESSION`
  6. Else if `abs(price - vwap) > 2.0 * atr` $\rightarrow$ `VWAP_MEAN_REVERSION`
  7. Else $\rightarrow$ `IDIOSYNCRATIC_FLOW`
- **Strengths**: Simple to implement, transparent logic trace.
- **Weaknesses**: Rigid prioritization order can mask strong sector divergence during moderate index drift; prone to edge-case toggling.

---

### Option B: Multi-Factor Weighted Continuous Decomposition (Recommended)
- **Logic**:
  1. Each driver candidate $k \in \mathcal{K}$ computes a signed raw score $S_k \in [-100, +100]$ and reliability $R_k \in [0.0, 1.0]$.
  2. Effective driver magnitude:
     $$M_k = |S_k| \times R_k$$
  3. Directional vector:
     $$D_k = \text{sign}(S_k) \in \{\text{BULLISH}, \text{BEARISH}, \text{NEUTRAL}\}$$
  4. Hysteresis Persistence: If an incumbent primary driver $k_{\text{prev}}$ exists, a new candidate $j$ replaces it if and only if:
     $$M_j > M_{k_{\text{prev}}} + \Delta_{\text{hysteresis}} \quad (\text{with } \Delta_{\text{hysteresis}} = 10.0)$$
     This guarantees rock-solid stability and eliminates rapid flipping on noisy candles.
  5. Evidence Partitioning:
     - All factors $i$ where $\text{sign}(S_i) == D_{\text{primary}}$ and $M_i \ge 15.0 \rightarrow$ `confirming_evidence`.
     - All factors $j$ where $\text{sign}(S_j) == -D_{\text{primary}}$ and $M_j \ge 15.0 \rightarrow$ `conflicting_evidence`.
- **Strengths**: Elegant mathematical foundation, zero arbitrary rule-order bias, built-in hysteresis against thrashing, unified confirming/conflicting evidence derivation.
- **Weaknesses**: Requires calibration of activation hurdles (e.g. 35.0, 20.0).

---

### Option C: Hybrid Regime-Conditioned Structural Engine
- **Logic**:
  1. Check `MarketRegime.gamma_regime` and `MarketRegime.volatility_regime`. If negative gamma & expanding vol, evaluate options/squeeze driver family first.
  2. If `MarketRegime.trend_regime` is active (`TREND_UP`/`TREND_DOWN`), compare Index vs Sector relative strength to determine broad vs sector driver.
  3. If `MarketRegime.trend_regime == RANGE`, evaluate Liquidity Absorption or VWAP Reversion.
- **Strengths**: Naturally reinforces the story told by Market Regime.
- **Weaknesses**: Cascades any potential regime classification ambiguity directly into Market Driver; reduces independent observability.
