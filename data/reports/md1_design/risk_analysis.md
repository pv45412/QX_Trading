# MD1 Architectural & Quantitative Risk Analysis

**Task**: MD1 Market Driver Engine Design  
**Authoritative Role**: Architecture & Quantitative Risk Specialist  
**Status**: DESIGN ARTIFACT (Read-Only Investigation)  

---

## 1. Risk Identification & Mitigation Matrix

| Risk ID | Risk Description | Severity | Likelihood | Mitigation Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **`RISK-01`** | **Driver Flip-Flopping / Thrashing**: Rapid switching between primary drivers on consecutive 5m bars due to noisy input oscillations. | High | Medium | Enforce **Hysteresis Buffer** ($\Delta = 10.0$ hurdle to unseat incumbent) and minimum persistence window. |
| **`RISK-02`** | **Lifecycle Boundary Creep**: Market Driver unintentionally vetoing valid setups or promoting `WATCH` to `ARMED`. | Critical | Low | Strict architectural isolation: Market Driver is an **explanatory observer** only. It does not touch `current_lifecycle_state`. |
| **`RISK-03`** | **Data Starvation / Feed Outage**: External feeds (e.g. GEX or Order Flow) become stale, drop out, or fail during volatile market moves. | High | Medium | Deterministic coverage hierarchy (`COMPLETE` $\rightarrow$ `PARTIAL` $\rightarrow$ `INSUFFICIENT`); fails closed to `UNAVAILABLE` if coverage $< 3$. |
| **`RISK-04`** | **Lookahead Leakage in Historical Replay**: Market Driver inadvertently using daily close or uncompleted higher timeframe candles. | Critical | Low | Enforce strict $T_{\text{event}} \le T_{\text{eval}}$ boundary and use only confirmed closed bars from BE2 multi-timeframe contract. |
| **`RISK-05`** | **Pipeline Latency Inflation**: Complex multi-asset lookups and correlations slowing pipeline evaluation beyond the 50 ms budget. | Medium | Low | All source inputs pre-computed and stored in `QXEvaluationContext`; engine evaluation is pure in-memory matrix math ($< 2.5$ ms). |
| **`RISK-06`** | **Operator Cognitive Overload**: Emitting too many secondary drivers or confusing conflicting evidence chips. | Medium | Low | Strictly bound output: Exactly 1 Primary Driver, maximum 2 Secondary Drivers, maximum 4 Confirming and 2 Conflicting evidence chips. |

---

## 2. Boundary Integrity Confirmation

### Explicit Lifecycle Veto Check:
- Market Driver **CANNOT** promote `WATCH` to `ARMED`.
- Market Driver **CANNOT** trigger an entry.
- Market Driver **CANNOT** veto `TRADEABLE` to `NOT_TRADEABLE`.
- Market Driver **CANNOT** modify Direction Engine factor weights or total score.

Any proposed change to give Market Driver lifecycle gating authority must be treated as a major architectural alteration requiring an explicit, dedicated human governance gate.
