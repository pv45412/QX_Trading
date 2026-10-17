# BE2 Causality Contract: Point-in-Time Synchronization & Lookahead Prevention

## 1. Core Principle: Zero Future Lookahead

In any multi-timeframe system, information leakage from the future into past evaluations is the primary source of model overfitting, unrealistic backtest results, and production failure.

**Causality Axiom**: At evaluation timestamp $T_{\text{eval}}$, an algorithm may only consume data whose completion and knowledge publication timestamp $T_{\text{avail}}$ satisfies:
$$T_{\text{avail}} \le T_{\text{eval}}$$

---

## 2. Candle Start vs. Close Timestamps & Incomplete HTF Bars

A critical point of ambiguity across market data vendors is timestamp labeling:
- Some providers label candles by their **start timestamp** (e.g. `10:00:00` for a 1-hour bar covering `10:00:00` to `10:59:59.999`).
- Other providers label candles by their **close timestamp** (e.g. `11:00:00`).

### The Lookahead Leakage Trap
If a bar is labeled by its start timestamp (`10:00:00`) and the evaluation occurs at `10:30:00`:
- Naive filtering with `bar_timestamp <= 10:30:00` would include the 1-hour bar.
- However, that 1-hour bar contains the high, low, and close of trades that will occur up to `11:00:00`!
- Consuming that bar at `10:30:00` constitutes a severe **30-minute future lookahead leak**.

### Strict Causality Rules:

1. **Explicit Candle End / Completion Boundary**:
   Every bar must have a deterministically computed completion timestamp:
   $$T_{\text{completion}} = T_{\text{start}} + \Delta_{\text{timeframe}}$$
   - For a `15m` bar starting at `10:00:00 UTC`, $T_{\text{completion}} = 10:15:00\text{ UTC}$.
   - For a `1h` bar starting at `10:00:00 UTC`, $T_{\text{completion}} = 11:00:00\text{ UTC}$.
   - For a `1d` bar for date `2026-09-17`, $T_{\text{completion}} = 16:00:00\text{ US/Eastern (20:00:00 UTC)}$ for RTH equity sessions.

2. **Incomplete Bar Prohibition for Structure**:
   - Any higher-timeframe bar where $T_{\text{completion}} > T_{\text{eval}}$ is defined as **INCOMPLETE**.
   - **Rule**: Incomplete HTF bars MUST NEVER be included in SMC pivot detection, BOS/CHoCH confirmation, or Order Block creation.
   - Only bars with $T_{\text{completion}} \le T_{\text{eval}}$ may be passed to `analyze_smc_structure`.

3. **Incomplete Bar Price Action (Micro-Context Only)**:
   - The current running price is already captured by the Setup/Execution timeframe.
   - HTF structure reflects confirmed structural swings, not mid-candle volatility.

---

## 3. Knowledge Timestamp & Feed Latency

In production, a candle closing at `11:00:00` is not received instantaneously at `11:00:00.000`:
- Vendor aggregation, network latency, and parsing introduce a publication delay $\delta_{\text{latency}}$.
- The bar's **Knowledge Timestamp** is:
  $$T_{\text{knowledge}} = \max(T_{\text{completion}}, T_{\text{received\_at}})$$
- For historical replay, an optional configured ingest delay (e.g. $+500\text{ms}$) can be enforced to test feed latency tolerance.

---

## 4. Stale Timeframe & Missing Data Handling (Fail-Closed Matrix)

| Scenario | Definition | System Action | Direction Impact | Lifecycle Impact |
| :--- | :--- | :--- | :--- | :--- |
| **HTF Fresh** | Last HTF bar closed $\le \text{max\_age}$ | Compute HTF SMC normally | Factor #7 active (`eff_weight = 0.10`) | Normal progression |
| **HTF Stale** | Last HTF bar closed $> \text{max\_age}$ bars ago | Degrade HTF factor reliability (`multiplier = 0.50`) | Factor #7 weight cut to `0.05` | Warning emitted in `reason_codes` |
| **HTF Missing** | No HTF bars available at or before $T_{\text{eval}}$ | Mark Factor #7 `UNAVAILABLE` (`reliability = 0.0`) | Coverage falls to `0.90` (status `STRONG` / `ADEQUATE`) | Depends on approved semantic model (Model 1 blocks; Model 2 degrades) |
| **Setup Missing** | No Setup TF bars available | Fail Closed | All factors `UNAVAILABLE` | **BLOCKED** (`NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP`) |
| **Calendar Mismatch** | Half-day / holiday / DST shift | Enforce exchange calendar cutoff | Bars beyond session close rejected | Preserves session boundaries |

---

## 5. Multi-Timeframe Bar Window Fingerprinting

Currently, `QXEvaluationResult.evaluated_bar_window_sha256` records the SHA256 of the setup timeframe bars.

To ensure deterministic multi-timeframe auditability:
1. Every timeframe evaluated must produce its own canonical bar window hash:
   - `bar_window_sha256_setup`
   - `bar_window_sha256_htf`
2. The `DataDependencyStatus` for each timeframe dependency records its independent hash, bar count, usable bar count, and incomplete candle count.
3. The root evaluation records a composite hash:
   $$\text{SHA256}(\text{setup\_hash} + \text{htf\_hash} + \text{timeframe\_mapping\_id})$$
   guaranteeing that identical inputs produce identical evaluations across live, shadow, and replay environments.
