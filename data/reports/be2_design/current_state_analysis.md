# BE2 Current State Analysis: Multi-Timeframe Usage & Architecture Coupling

## Executive Summary

This investigation analyzes how timeframe context is currently ingested, processed, and coupled across all phases of the QX Platform (Phases 3–10), the opportunity service, historical replay, and the frontend web workspace.

---

## 1. Pipeline Execution Trace & Timeframe Flow

The core evaluation is orchestrated by `run_pipeline(ctx: QXEvaluationContext, config: RulesEngineConfig)` in `src/qx/pipeline/orchestrator.py`:

```
                    ┌─────────────────────────┐
                    │   QXEvaluationContext   │
                    │   - symbol: "SPY"       │
                    │   - timeframe: "5m"     │
                    │   - bars: DataFrame     │
                    │   - htf_structure_state │
                    └───────────┬─────────────┘
                                │
       ┌────────────────────────┼────────────────────────┐
       ▼                        ▼                        ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  Phase 4 SMC │         │ Phase 5      │         │ Phase 6      │
│  Structure   │         │ Market       │         │ Direction    │
│  (Single TF) │────────►│ Regime       │────────►│ Engine       │
│              │         │ (Single TF)  │         │ (7 Factors)  │
└──────────────┘         └──────────────┘         └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ Phase 7      │
                                                  │ Playbooks    │
                                                  │ (ORB, PB, LS)│
                                                  └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ Phase 7.5    │
                                                  │ Triggers     │
                                                  └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ Phase 8      │
                                                  │ Tradeability │
                                                  └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ Phase 9-10   │
                                                  │ Options &    │
                                                  │ Risk         │
                                                  └──────────────┘
```

### Stage-by-Stage Timeframe Usage:

1. **Point-in-Time Bar Filtering (`src/qx/pipeline/point_in_time.py`)**:
   - `filter_bars_at_or_before(ctx.bars, evaluation_timestamp)` filters a single DataFrame.
   - Evaluated bar window hash is computed via `evaluated_bar_window_sha256(visible_bars, ctx.timeframe)`.
   - **Coupling**: Exactly one bar window and one timeframe string are hashed and recorded.

2. **Phase 4 Market Structure (`src/qx/structure/smc_suite.py`)**:
   - `analyze_smc_structure(bars=visible_bars, timeframe=ctx.timeframe, ...)` operates on a single sequence of bars.
   - Pivots, BOS/CHoCH events, and Order Blocks are computed strictly for `ctx.timeframe`.
   - `_completion_timestamp(value, timeframe)` handles minute strings (`5m`, `15m`), but assumes non-minute intervals (`1h`, `1d`) require no minute offset.

3. **Phase 5 Market Regime (`src/qx/regime/market_regime.py`)**:
   - Consumes the single-timeframe structure result, ATR, and GEX data. No secondary timeframe inputs.

4. **Phase 6 Direction Engine (`src/qx/direction/direction_engine.py`)**:
   - Evaluates 7 factors:
     1. Market Structure (`configured_weight = 0.25`)
     2. VWAP (`configured_weight = 0.15`)
     3. EMA Alignment (`configured_weight = 0.15`)
     4. Delta Volume (`configured_weight = 0.15`)
     5. Sector Relative Strength (`configured_weight = 0.10`)
     6. Market Alignment (`configured_weight = 0.10`)
     7. **Higher Timeframe Structure (`configured_weight = 0.10`)**
   - **Existing Hook**: Factor #7 (`compute_higher_timeframe_factor`) already exists! It accepts `htf_structure_state: Optional[str]` and `htf_age_bars: Optional[int]`.
   - **Current Flaw / Void**: In `QXEvaluationContext`, `htf_structure_state` defaults to `"UNKNOWN"` and `htf_age_bars = 9999`. Unless manually populated by an external caller, it contributes `0.0` effective weight and status `UNAVAILABLE`. There is currently no upstream pipeline stage or coordinator that automatically analyzes HTF bars to populate this factor.

5. **Phase 7 Playbooks (`src/qx/playbooks/`)**:
   - `PlaybookContext` stores `timeframe: str = "5m"`.
   - Candidates (Pullback, ORB, Liquidity Sweep) inherit this single timeframe.
   - None of the playbooks currently cross-reference a secondary or higher timeframe order block or liquidity level.

6. **Phase 7.5 Triggers (`src/qx/triggers/`)**:
   - Evaluates whether the armed setup has triggered on the latest bar of `armed_eval.timeframe`.
   - Lookback for armed expiration (`max_armed_bars = 12`) is scaled by `armed_eval.timeframe`.

7. **Phase 8 Tradeability (`src/qx/tradeability/`)**:
   - Uses `ctx.timeframe` for:
     - `_timeframe_seconds(ctx.timeframe)` (converting `5m` -> 300s, `1h` -> 3600s).
     - `max_tradeability_delay_bars` mapping.
     - RVOL baseline cache key: `(symbol, timeframe, time_slot, lookback_sessions, ...)`.

8. **Phases 9 & 10 Options Expression & Risk (`src/qx/options_expression/`, `src/qx/portfolio/`)**:
   - Independent of candle timeframe, driven by expiration cycle (DTE) and capital limits.

---

## 2. Opportunity Service & Persistence (`src/qx/opportunities/`)

- **Schema**: The SQLite `opportunities` table defines:
  - `timeframe TEXT NOT NULL`
  - `horizon_context TEXT` (optional, e.g. `'DAY'`, `'SWING'`, `'INVEST'`)
  - `bar_window_sha256 TEXT NOT NULL`
  - `idempotency_key TEXT UNIQUE`
  - `stream_key TEXT NOT NULL` (`canonical_stream_key(symbol, timeframe, horizon_context)`)
- **API**: `GET /api/v2/qx/opportunities` accepts query parameters `timeframe` and `horizon_context`.
- **Constraint**: Changing how `timeframe` is stored or queried could affect stream uniqueness and deduplication if not designed additively.

---

## 3. Historical Replay (`src/qx/pipeline/adapters.py`)

- `HistoricalReplayAdapter` processes a single series of historical bars.
- Evaluates bar completion via `_bar_completion_timestamp(current_bar, self.timeframe)`.
- Currently, `_bar_completion_timestamp` only recognizes minute intervals (`m`). If passed `1h` or `1d`, it returns the start timestamp without adding duration.
- Replaying across multiple synchronized timeframes currently does not exist.

---

## 4. Frontend UI Horizon Handling (`web/src/`)

- The UI surfaces a horizon toggle: `['DAY', 'SWING', 'INVEST']`.
- In `web/src/QXOpportunitiesWorkspace.jsx` and `QXTodayWorkspace.jsx`:
  ```javascript
  const timeframeByHorizon = {DAY: '5m', SWING: '1h', INVEST: '1d'};
  ```
- Selecting a horizon currently simply sets `context.timeframe` to that single timeframe.
- The UI does not display higher timeframe context or multi-timeframe alignment scores.

---

## 5. Architectural Constraints & Safest Integration Points

1. **Preserve Single-Timeframe Execution Path**:
   - `QXEvaluationContext` and `run_pipeline` must continue to support single-timeframe execution for backward compatibility and tests.
2. **Safe Integration Point for HTF Structure**:
   - Factor #7 in `evaluate_direction_engine` is already configured with weight `0.10` and handles `htf_structure_state`.
   - Feeding a point-in-time verified HTF SMC result into `ctx.htf_structure_state` directly lights up Factor #7 without breaking any existing engine contracts.
3. **Multi-Timeframe Container Contract**:
   - Rather than forcing one monolithic DataFrame, `QXEvaluationContext` should accept a structured `multi_timeframe_bars: Dict[str, pd.DataFrame]` or a point-in-time HTF snapshot cache.
   - The primary evaluation timeframe remains the "Setup / Execution" timeframe, while secondary timeframes provide validated background context.
