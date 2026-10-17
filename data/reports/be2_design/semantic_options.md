# BE2 Semantic Options: Multi-Timeframe Meaning & Models

## 1. Defining Multi-Timeframe Roles

In institutional quantitative analysis, multi-timeframe relationships are organized into functional tiers:

| Timeframe Role | Primary Function | Typical Content | Lifecycle Impact |
| :--- | :--- | :--- | :--- |
| **Execution Timeframe** | Precision timing, micro-trigger, tight invalidation | 1m, 5m, 15m bars, micro-swings, tight FVG/OB | Determines exact fill price & micro stop |
| **Setup Timeframe** | Playbook formation, pattern recognition | 5m, 15m, 1h bars, primary SMC structure, ATR | Drives primary Lifecycle State (WATCH -> ARMED -> TRIGGERED) |
| **Higher Timeframe (HTF)** | Directional bias, structural trend, major liquidity | 15m, 1h, 4h, Daily bars, major BOS/CHoCH | Guides Direction Score & Evidence Coverage |
| **Macro Timeframe** | Macro regime, broader market driver context | Daily, Weekly, SPY/QQQ benchmark alignment | Establishes overall market risk environment |

---

## 2. Horizons: DAY vs. SWING vs. INVEST

The meaning of each timeframe tier shifts according to the trader's stated horizon:

### A. DAY Horizon
- **Execution**: 1m (or 5m)
- **Setup**: 5m (or 15m)
- **HTF**: 15m (or 1h)
- **Macro**: Daily (RTH trend, yesterday's high/low)
- *Dynamics*: Intraday momentum, opening range expansion, mean reversion to session VWAP. Trades expire at session close (EOD).

### B. SWING Horizon
- **Execution**: 15m (or 1h)
- **Setup**: 1h (or 4h)
- **HTF**: Daily (1d)
- **Macro**: Weekly (1w)
- *Dynamics*: Multi-day trend following, weekly liquidity pools, structural swings holding across overnight sessions.

### C. INVEST Horizon
- **Execution**: Daily (1d)
- **Setup**: Weekly (1w)
- **HTF**: Monthly (1M)
- **Macro**: Quarterly / Macro Index drivers
- *Dynamics*: Long-term capital allocation, quarterly earnings cycles, major macro regimes.

---

## 3. Alternative Semantic Models for Multi-Timeframe Interaction

We outline three distinct semantic models governing how higher and lower timeframes interact.

### Model 1: Strict Structural Veto / Confirmation Gate
- **Semantic Rule**: The Setup timeframe may ONLY transition to `ARMED` or `TRIGGERED` if the Higher Timeframe is explicitly confirmed in the same direction (or optionally neutral).
- **Conflict Handling**:
  - Setup = BULLISH, HTF = BEARISH -> **LIFECYCLE VETOED / BLOCKED**.
  - Setup = BEARISH, HTF = BULLISH -> **LIFECYCLE VETOED / BLOCKED**.
  - Setup = BULLISH, HTF = NEUTRAL -> Allowed with warning.
- **Advantages**:
  - Maximum trend alignment; prevents counter-trend trap entries.
  - High win-rate potential; disciplined institutional risk control.
- **Risks & Drawbacks**:
  - Drastically reduces opportunity count (high false rejection rate during early trend reversals).
  - Incapable of capturing mean-reversion setups (e.g. Liquidity Sweep at HTF support).
  - Requires both timeframes to have zero missing data, or else fails closed to `BLOCKED`.

### Model 2: Tiered Evidence / Weighted Directional Bias (Soft Gate)
- **Semantic Rule**: The Setup timeframe remains the sole driver of the Lifecycle State (`WATCH` -> `ARMED` -> `TRIGGERED`). The Higher Timeframe acts as an evidence factor (specifically Factor #7 in the Direction Engine).
- **Conflict Handling**:
  - Setup = BULLISH, HTF = BEARISH:
    - HTF Factor scores `-100.0` with `effective_weight = 0.10`.
    - Direction Score is degraded mathematically.
    - If overall Direction Score falls below the playbook threshold (e.g. `< 20.0`), the playbook does not arm. If Direction Score remains sufficiently positive due to other factors (e.g. strong Delta + VWAP), the setup can still trigger.
  - Missing HTF:
    - HTF Factor is marked `UNAVAILABLE` with `reliability = 0.0`.
    - Total Evidence Coverage is reduced from `1.00` to `0.90` (status `ADEQUATE` or `STRONG`).
    - The setup is NOT blocked; it proceeds with degraded coverage.
- **Advantages**:
  - Seamlessly integrates with the existing 7-factor Direction Engine without breaking current contracts.
  - Graceful degradation under missing or delayed HTF market data.
  - Accommodates mean-reversion playbooks where micro-structure turns before macro-structure.
- **Risks & Drawbacks**:
  - Allows occasional trades against prevailing HTF trend if intraday delta/VWAP are strong.

### Model 3: Asymmetric Horizon-Specific Rules
- **Semantic Rule**: Rules differ by Horizon:
  - **DAY**: Uses Model 2 (Tiered Evidence). Intraday scalps and sweeps are permitted even if HTF is counter-trend, provided intraday liquidity supports it.
  - **SWING**: Requires HTF Directional Concordance (HTF cannot be opposing, but neutral is permitted).
  - **INVEST**: Strict Model 1 (HTF Veto). No long investments allowed if Monthly structure is Bearish.
- **Advantages**:
  - Respects the financial reality that day trading and long-term investing have fundamentally different relationship dynamics with higher-timeframe trends.
- **Risks & Drawbacks**:
  - Higher architectural complexity; requires horizon-conditioned validation pipelines.
