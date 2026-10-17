# MD1 Replay, Shadow, and Test Validation Plan

**Task**: MD1 Market Driver Engine Design  
**Authoritative Role**: Replay / Validation & QA Specialist  
**Status**: DESIGN ARTIFACT (Read-Only Investigation)  

---

## 1. Validation Strategy Overview

The Market Driver Engine must satisfy four rigorous verification gates before promotion:
1. **Unit & Invariant Verification**: Mathematical bounds, enum schemas, hysteresis stability, and sign-alignment of confirming/conflicting evidence.
2. **Causality & Lookahead Prevention**: Strict point-in-time filtering across multi-asset feeds ($T \le T_{\text{eval}}$).
3. **Replay vs. Live Parity**: Identical inputs processed in Historical Replay and Live production must yield bit-for-bit identical driver IDs, strength, and evidence.
4. **Stress & Missing-Data Degradation**: Fail-closed behavior when feeds drop, go stale, or corrupt.

---

## 2. Invariant Test Matrix

| Test ID | Invariant Verified | Input Condition | Expected Result |
| :--- | :--- | :--- | :--- |
| `INV-MD-01` | **Coverage Hurdle** | Sources available $< 3$ (e.g. only underlying bars). | `status = "UNAVAILABLE"`, `primary_driver = null`, reason `INSUFFICIENT_EVIDENCE_COVERAGE`. |
| `INV-MD-02` | **Partial Transparency** | 4 sources available (gamma missing). | `status = "PARTIAL"`, `missing_sources = ["gamma"]`, driver emitted with partial badge. |
| `INV-MD-03` | **Point-in-Time Wall** | Bar series with candles timestamped $> T_{\text{eval}}$. | Filtered strictly at $T_{\text{eval}}$; future candles completely invisible. |
| `INV-MD-04` | **Hysteresis Stability** | Incumbent driver $M=60.0$; candidate driver $M=65.0$ ($\Delta = 5.0 < 10.0$). | Incumbent retained; persistence increments duration; reason `HYSTERESIS_MAINTAINED`. |
| `INV-MD-05` | **Hysteresis Transition**| Incumbent driver $M=60.0$; candidate driver $M=72.0$ ($\Delta = 12.0 > 10.0$). | Candidate promoted to Primary; persistence state reset to `NEW`, duration reset to 0. |
| `INV-MD-06` | **Evidence Orthogonality**| Primary is `INDEX_RISK_ON` (Bullish). Positive delta and bullish structure present; negative sector present. | Positive delta & structure $\rightarrow$ `confirming_evidence`; negative sector $\rightarrow$ `conflicting_evidence`. |
| `INV-MD-07` | **Zero Client Inference** | Web client receives `UNAVAILABLE` payload. | Renders "Market driver unavailable"; does not derive driver from regime or price. |
| `INV-MD-08` | **Deterministic Idempotency**| Same `QXEvaluationContext` evaluated 1,000 times. | Exact same output SHA256 every single time. |

---

## 3. Replay & Shadow Parity Protocol

### Historical Replay Protocol
- Replay through major historical market regimes:
  - **Trend Day**: Persistent `INDEX_RISK_ON` / `INDEX_RISK_OFF` (low flip rate, $> 90$ minutes continuous persistence).
  - **Chop / Range Day**: Transition between `LIQUIDITY_ABSORPTION`, `VWAP_MEAN_REVERSION`, and `GAMMA_PINNING`.
  - **Macro Catalyst Day**: `MACRO_CATALYST` triggers during CPI/FOMC release window, cleanly transitioning to post-announcement directional expansion.
- **Flip Rate Metric**: Total driver transitions per 6.5-hour trading session. Baseline target: $\le 4$ primary driver switches per day to avoid cognitive fatigue for the operator.

### Shadow Validation Protocol (Stage OBS1)
- Run parallel shadow engine alongside live pipeline.
- Measure execution latency: target $< 3.5$ ms per evaluation (well within the overall 50 ms pipeline budget).
- Monitor telemetry for telemetry anomalies or unhandled exceptions.
