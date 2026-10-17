# BE2 Risk Analysis: Multi-Timeframe Systemic & Quantitative Risks

## 1. Latency & Computational Load Risks

- **Risk**: Ingesting and analyzing SMC structures across 2–3 timeframes concurrently multiplies CPU execution time.
  - Phase 4 SMC analysis currently takes ~5–12ms per bar series.
  - Running SMC on 1m, 5m, and 15m simultaneously per symbol could triple pipeline latency from ~15ms to ~45ms per evaluation.
- **Mitigation**:
  - Higher timeframe structures do not need to be recomputed on every 1m or 5m tick! A 1-hour bar only closes once every 60 minutes.
  - **HTF Structure Caching**: Precompute and cache HTF structure upon candle close. The 5m pipeline simply reads the cached, immutable HTF structure snapshot, reducing incremental latency to `< 0.2ms`.

---

## 2. Market Data Provider Rate Limits & Ingestion Volume

- **Risk**: Requesting multi-timeframe historical bars for large universes (e.g. 100 symbols across 3 timeframes = 300 active bar streams) could breach provider rate limits (e.g. Schwab API quotas).
- **Mitigation**:
  - Bar Resampling: Resample 1m base bars into 5m and 15m candles in-memory using deterministic calendar aggregation rather than issuing separate HTTP requests.
  - Fail-closed fallback: When HTF streams are rate-limited, gracefully degrade to single-timeframe evaluation (Option B) rather than crashing the pipeline.

---

## 3. Asymmetric Timeframe Conflict & Whipsaw

- **Risk**: Fast intraday setups frequently form during counter-trend pullbacks on the higher timeframe (e.g., a bullish 5m pullback occurring inside a daily downtrend).
  - Under strict veto models (Option A), these trades are rejected, preventing profitable mean-reversion trades.
  - Under loose models, counter-trend trades risk high slippage and adverse selection if the macro trend resumes suddenly.
- **Mitigation**:
  - Human review must explicitly decide whether counter-trend intraday plays are allowed (Option B or C) or strictly banned (Option A).
  - The system will enforce the chosen policy deterministically without ad-hoc overrides.

---

## 4. Lookahead Leakage via Real-Time Tick Aggregation

- **Risk**: Real-time websocket feeds may deliver trade prints that update an open HTF bar (e.g. updating the high of a current 1h bar). If that partially completed bar is fed into pivot detection, future leakage occurs relative to an earlier evaluation timestamp.
- **Mitigation**:
  - Hard gate: Only finalized, closed bars with explicit $T_{\text{completion}} \le T_{\text{eval}}$ can enter SMC structure analysis.
  - Real-time ticks only update the current execution bar.

---

## 5. Persistence & Schema Migration Risks

- **Risk**: Altering the `opportunities` table schema or modifying `idempotency_key` generation to include multi-timeframe hashes could invalidate existing records or cause migration drift.
- **Mitigation**:
  - Additive changes only: The primary `timeframe` column continues to store the primary Setup timeframe (e.g. `5m`).
  - Multi-timeframe details are stored within `data_dependencies` and the `decision_payload` JSON.
  - Database schema fingerprints remain intact.
