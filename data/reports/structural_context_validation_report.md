# QX Structural Context Validation and Data Remediation

Generated: 2026-09-16  
Pipeline: `core_v1`  
Status: **PASS**

## 1. Exact Cause of `NO_STRUCTURAL_CONTEXT`

The canonical Phase 3 model publishes structure state as `SMCAnalysisResult.regime`,
but Market Regime, Direction, and Trend Pullback consumed `state`. Because the full
structure object was present, their explicit `structure_state` fallback was skipped.
Confirmed bullish/bearish structure was therefore flattened to `NEUTRAL`, producing
`RANGE`, a neutral structure factor, and a failed pullback structure gate.

Additional contract losses compounded the issue:

- `latest_event` was stringified instead of forwarding `latest_event.event_type`.
- Canonical order blocks used `direction`/`order_block_id`, while Pullback expected
  `type`/`ob_id`.
- Order blocks, protected swings, and liquidity pools were not forwarded to Phase 6.
- Default playbook reason codes mislabeled unrelated coverage, liquidity, and ORB
  failures as `NO_STRUCTURAL_CONTEXT`.

## 2. Representative BOS Trace

- Symbol/timeframe: `SPY:1m`.
- Bar start: `2026-09-16T18:32:00Z`; evaluation/knowledge: `18:33:00Z`.
- Event: `BEARISH_BOS`, `BEARISH -> BEARISH`, source
  `PIVOT_LOW_42_1m`.
- Protected bearish swing: high `761.23`, pivot `PIVOT_HIGH_48_1m`, known at
  `18:19:00Z`, promoted at `18:33:00Z`.
- Phase 6 received the exact structure object and canonical EQL identity
  `EQL_PIVOT_LOW_24_1m_PIVOT_LOW_42_1m` with both source pivots.
- Result: Liquidity Sweep `ARMED`; Pullback remained blocked only by
  `INSUFFICIENT_EVIDENCE_COVERAGE`.

## 3. Representative CHoCH Trace

- Symbol/timeframe: `QQQ:1m`.
- Bar start: `2026-09-16T18:27:00Z`; evaluation/knowledge: `18:28:00Z`.
- Event: `BEARISH_CHOCH`, `BULLISH -> BEARISH`, source
  `PIVOT_LOW_24_1m`.
- Protected bearish swing: high `711.65`, pivot `PIVOT_HIGH_48_1m`, known at
  `18:19:00Z`, promoted at `18:28:00Z`.
- Result: active bias `BEARISH`; Liquidity Sweep `ARMED` with canonical EQL source
  identity and timestamps.

## 4. Structure to Playbook Contract

- State: `SMCAnalysisResult.regime` is consumed by Regime, Direction, and Pullback.
- Event: `latest_event.event_type` is passed to Direction.
- Order blocks: canonical objects pass unchanged; consumers accept canonical and
  legacy aliases.
- Liquidity: protected swings and EQH/EQL pools pass unchanged through
  `PlaybookContext.liquidity_levels`.
- Provenance: protected swings retain pivot ID/knowledge time; pools retain stable
  pool ID, constituent pivot IDs, and latest constituent knowledge time.
- Legacy `session_levels` remains supported for PDH/PDL/ORB inputs.

## 5. Context Persistence

Persistence is correct. The engine is intentionally stateless per invocation but
reconstructs state over the entire point-in-time prefix. A protected/no-break trace
at `SPY:1m 18:11Z` retained bearish context and protected high `760.06` after the
earlier `BEARISH_CHOCH`. Replay now evaluates minute bars only at candle completion.

## 6. Repairs

- Added canonical `regime` and event-schema compatibility.
- Forwarded canonical order blocks and structural liquidity objects.
- Preserved order-block, swing, and pool identities and knowledge timestamps.
- Corrected playbook reason attribution without changing gates.
- Made replay evaluation and SMC knowledge timestamps candle-completion safe.
- Added deterministic adversarial fixtures for BOS, CHoCH, persistence, future
  pivots, symbol/timeframe isolation, Phase 6 consumption, and provenance.

No pivot, BOS/CHoCH, protected-swing, playbook, direction, volatility, R:R, options,
or portfolio threshold was changed.

## 7. Stale Schwab Root Cause

- The original 27 stale intraday observations came from Schwab price-history
  requests without `endDate`; responses stopped at the prior session. Supplying the
  current request end time returned current-session data.
- The final report was generated shortly after market close. Ten `1m` series were
  flagged stale because the simple age threshold compared the final `19:59Z` bar to
  `20:08Z`; this is a session-aware reporting gap, not cache reuse or missing bars.
- Nine option chains were stale because chain freshness intentionally uses the oldest
  contract quote. Latest snapshot timestamps were recent, but oldest-contract ages
  ranged into several hours.
- Final stale count: `19` (`10` one-minute bars, `9` option chains); cache timestamps
  were null because all probes were direct provider calls; causality violations: `0`.
- Freshness thresholds and fail-closed option policy were not relaxed.

## 8. SPX Compatibility

Read-only live probes proved Schwab requires `$SPX` for quote, price history, and
option chain. Canonical QX identity remains `SPX`. Final coverage has no missing SPX
series or provider failures. SPX quote, 1m/5m/15m bars, and options all returned data.

## 9. Dotenv/Test Isolation

Unit collection now disables implicit dotenv loading, removes inherited QX/legacy AI
configuration from the pytest child process, and disables the Pydantic `.env` source
for unit defaults. Explicit test env files still work. Production settings and local
`.env` behavior are unchanged; no secret values were emitted.

## 10. Structure Scan Amplification

- `68,850` prefix rows processed from `2,520` distinct source bars.
- Repeated rows: `66,330`; amplification: `27.3214x`.
- Structure latency: p50 `40.06ms`, p95 `54.33ms`, p99 `60.51ms`.
- Replay throughput: `1,020` observations in `44.86s`, or `22.74 obs/s`.
- Cause: every replay observation copies and rescans the complete prefix, including
  pivots, ATR, state machine, order-block lifecycle, and protected-swing searches.
- No optimization was implemented. Incremental state, causal precomputation,
  memoization, and redundant-filter removal remain recommendations only.

## 11. Tests and Checker Gates

- Focused structural suite: `143 passed`.
- Final maintained unit suite: `2,259 passed`, `2 skipped`, `0 failed`.
- Regression suite: `18 passed`, `0 failed`.
- Preflight: all `13/13` service/UI checks passed with the local backend running.
- Architecture Checker: `PASS`.
- Quant/Data Semantics Checker: `PASS` after two repair cycles.
- QA Gatekeeper: `PASS`; report security scan found no credentials, tokens, private
  keys, or raw account identifiers.
- Performance Checker: `PASS`; profile-only constraint preserved.

## 12. Lifecycle Distribution After Repair

Across `1,020` canonical observations:

- `NO_SETUP`: `922`
- `WATCH`: `32`
- `ARMED`: `66`
- `TRIGGERED`, `TRADEABLE`, options, and portfolio states: `0`
- `WATCH -> ARMED`: `7`
- Regime: `TREND_DOWN 417`, `RANGE 358`, `TREND_UP 245`
- Session: `BALANCED 1,020`

Today’s downside sanity case showed bearish BOS and `TREND_DOWN` on SPX, SPY, and QQQ
at 5m/15m, protected bearish highs on SPX/SPY/QQQ 15m, SPY/QQQ below observed VWAP,
and opening-range downside breaks on all three. The canonical pipeline reached
`ARMED` on SPX 5m/15m, SPY 15m, and QQQ 5m/15m. Coverage remained `INSUFFICIENT`
because canonical VWAP, EMA, delta, sector/market alignment, and higher-timeframe
inputs were unavailable or defaulted; volatility remained `NORMAL`, session remained
`BALANCED`, and ORB inputs remained unavailable. Those are explicit future data
contract gaps, not grounds for threshold or playbook changes.
