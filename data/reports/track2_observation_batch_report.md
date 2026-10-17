# QX Track 2 Autonomous Observation Batch — Consolidated Report

Date: 2026-09-16  
Canonical pipeline version: `core_v1`  
Status: **Track 2C PASS / Track 2E PASS / Track 2G PASS**  
Execution: **disabled**  
Phase 11: **not started**

## 1. Performance Baseline

The baseline exercised the canonical V2 POST route across the requested symbols (`SPY`, `QQQ`, `SPX`, `NVDA`, `AAPL`, `MSFT`, `TSLA`, `AMD`, `JPM`, `XOM`) and requested timeframes (`1m`, `5m`, `15m`, `1d`). It collected 120 provider-disabled API samples and 11 configured-provider API samples.

Only correctly sourced workloads contribute to valid latency distributions. Of 40 requested symbol/timeframe combinations, 9 daily workloads were valid, 27 intraday combinations resolved to daily cache files and were classified `TIMEFRAME_SOURCE_MISMATCH`, and all four SPX combinations were unavailable. The production cache-selection behavior was measured but not changed.

The configured read-only Schwab providers were called for all 11 live-mode samples. Every option-chain and account acquisition returned `ERROR` because authentication was unavailable. No provider result was relabeled as successful, no snapshot was fabricated, and no secret was logged.

## 2. Pipeline p50 / p95 / p99

| Measurement | Samples | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|
| Cached API, valid inputs | 27 | 287.26 | 723.74 | 887.27 |
| Cached pipeline `total_ms` | 27 | 268.12 | 653.89 | 799.80 |
| Configured-provider API, valid inputs | 9 | 280.34 | 406.64 | 428.13 |
| Configured-provider pipeline `total_ms` | 9 | 258.21 | 386.70 | 407.88 |
| Browser-to-local-V2 evaluation | 2 | 440.90 | 537.65 | 546.25 |
| Frontend lifecycle interaction | 8 | 27.60 | 50.49 | 52.90 |
| Fixture lifecycle render | 9 | 8.60 | 11.60 | 12.24 |
| Live lifecycle render | 5 | 1.60 | 26.60 | 28.92 |

Python API measurements use in-process FastAPI `TestClient`, so they exclude network/server transport overhead. Browser measurements include the local Vite proxy and local Uvicorn API. The browser sample count is intentionally reported and is too small for production capacity inference.

## 3. Stage Bottlenecks

The structure stage dominates measured execution:

| Stage | Cached p50 ms | Cached p95 ms | Cached p99 ms | Executed / skipped |
|---|---:|---:|---:|---:|
| Structure | 264.69 | 644.33 | 789.67 | 27 / 0 |
| Playbooks | 2.27 | 6.47 | 7.04 | 27 / 0 |
| Direction | 0.16 | 0.28 | 0.40 | 27 / 0 |
| Regime | 0.07 | 0.10 | 0.11 | 27 / 0 |
| External I/O | 10.21 | 61.28 | 78.38 | 27 / 0 |
| Trigger | — | — | — | 0 / 27 |
| Tradeability | — | — | — | 0 / 27 |
| Options expression | — | — | — | 0 / 27 |
| Portfolio risk | — | — | — | 0 / 27 |

Structure consumed approximately 98% of mean pipeline execution time. This is an observational bottleneck only; no optimization or rule change was applied. Skipped stages remain `SKIPPED`/null rather than zero milliseconds.

Snapshot-store operations measured p50 1.91 ms, p95 2.73 ms, and p99 3.14 ms across 13 operations. SQLite reported WAL mode, 10,000 ms busy timeout, synchronous mode `NORMAL`, zero busy observations, and zero SQLite errors.

Repeated external I/O was visible: the read-only account provider was called once per symbol evaluation even though it is not symbol-specific. This is a recommendation candidate only; no cache or architecture was introduced.

## 4. Replay Throughput

- Source: `data/cache/bars/intraday/SPY_10d_5m.csv`
- Input bars: 60
- Warmup bars: 50
- Canonical observations: 10
- Elapsed: 0.871 seconds
- Throughput: 11.49 observations/second
- Transitions: 0
- Outcomes: 0

The previously accepted bounded replay finding remains valid: low or zero setup/transition counts are observations, not failures, and no thresholds were changed.

## 5. Shadow Observation Counts

The approved batch persisted 20 genuine, non-executing daily observations through the canonical V2 route and `run_pipeline()`:

- `NO_SETUP`: 18
- `BLOCKED`: 2
- Total: 20
- Pipeline version `core_v1`: 20
- Errors: 0
- Cumulative approved daily observations in the bounded query: 80
- Persisted non-daily records excluded from this analysis because of timeframe-source ambiguity: 3

Options and account snapshots were unavailable for every batch observation. Downstream options and portfolio stages therefore remained unavailable/skipped; no snapshots were fabricated.

## 6. Lifecycle Transition Counts

| Transition | Count |
|---|---:|
| `WATCH -> ARMED` | 0 |
| `ARMED -> TRIGGERED` | 0 |
| `TRIGGERED -> TRADEABLE` | 0 |
| Any other state change | 0 |

Two collection cycles produced stable states for every symbol/timeframe series. No rule was loosened to create transitions.

## 7. BLOCKED / NO_SETUP Distribution

| State / stop reason | Batch count |
|---|---:|
| `NO_SETUP` | 18 |
| `BLOCKED` | 2 |
| `NOT_TRADEABLE` | 0 |
| `OPTIONS_NOT_SUITABLE` | 0 |
| `PORTFOLIO_VETOED` | 0 |
| `NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP` | 2 |

The two blocked records are the two SPX cycles with no usable cached bars.

## 8. Playbook / Regime Distribution

| Dimension | Distribution |
|---|---|
| Primary candidate | `playbook_a_pullback`: 18; unavailable: 2 |
| Lifecycle | `NO_SETUP`: 18; `BLOCKED`: 2 |
| Trend regime | `RANGE`: 18; unavailable: 2 |
| Direction | `NEUTRAL`: 18; unavailable: 2 |
| Evidence coverage | `INSUFFICIENT`: 18; unavailable: 2 |

The playbook candidate count does not imply a valid setup or trade.

## 9. Data-Quality Findings

1. **Timeframe provenance:** daily cache files currently satisfy many intraday route requests. These 82 measured samples (81 cached-mode repetitions and one live-mode sample) were excluded from valid latency statistics.
2. **Stale bars:** 18 batch observations had bars; 14 were older than seven days and 4 were between one and seven days. Median age was approximately 8.60 days; maximum age was approximately 107.64 days.
3. **Missing SPX bars:** both SPX batch evaluations were correctly blocked.
4. **Provider availability:** all 11 option-chain and all 11 account acquisition attempts failed authentication; successful live-provider latency is unavailable.
5. **Snapshot availability:** zero canonical option snapshots and zero account snapshots were available through the observation cutoff.
6. **Point-in-time audit:** zero future `data_as_of` violations occurred. The analyzer now exposes any future timestamp as `FUTURE_DATA_AS_OF` rather than clamping it.
7. **Frontend scope:** actual V2 evaluation latency, request duplication, polling, interactions, and lifecycle renders were measured. Scanner refresh and chart redraw counts were explicitly unavailable because those features are absent from the bounded lifecycle harness.

## 10. Legacy Migration Inventory

The complete inventory is in `migration_matrix.md`. It covers:

- Canonical pipeline, V2 API, lifecycle adapter/component: `KEEP`.
- V1 `SignalService`, scanner route, legacy SMC signal engine: `DEPRECATE` pending consumer migration.
- Legacy direction, strategy/trade construction, and market regime calculations: `REPLACE` only through tested compatibility boundaries.
- Risk, telemetry, AI review, ideas, trading-suite composition, and execution dependencies: `ADAPT`.
- Unreferenced legacy scanner regime service: `DEPRECATE`, with removal still requiring import verification and human approval.
- Legacy removal: `REMOVE_LATER` only after all dependency, regression, rollback, and human approval gates pass.

No legacy module, API route, frontend flow, or execution path was deleted or rerouted.

## 11. Migration Dependency Graph

```text
timeframe/provider provenance
    -> stable V2 API
        -> sustained shadow evidence
            -> HUMAN_REQUIRED scanner UI contract decision
                -> feature-flagged consumer migration
                    -> V1 route deprecation
                        -> legacy scanner modules eligible for REMOVE_LATER

canonical regime compatibility adapter
    -> watchlist/report/scan/SPX consumers
        -> old market regime eligible for REMOVE_LATER

canonical lifecycle/read models
    -> ticker service migration
        -> legacy SMC signal engine eligible for REMOVE_LATER

future human-approved Phase 11 architecture
    -> execution validation and broker-write approval
        -> execution migration
            -> execution dependencies eligible for REMOVE_LATER
```

## 12. Known Risks

- Intraday/daily cache ambiguity is a correctness blocker for broader intraday V2 adoption.
- Structure analysis is the dominant latency bottleneck; no optimization has been validated.
- Current shadow data has zero lifecycle transitions and no downstream snapshot coverage.
- Current bars are stale for most observed symbols.
- Successful external-provider performance is unknown because credentials were unavailable; no credential changes were made.
- The `QXOptionsScanner` account-equity/ranked-strategy contract materially differs from the symbol-only V2 lifecycle contract. Selecting the target architecture is `HUMAN_REQUIRED`.
- Browser V2 timing has only two samples; scanner refresh and chart redraw baselines remain unavailable.

## 13. Test and Checker Results

### Automated tests

- Focused observation tests: 7 passed.
- Focused Track 1/Track 2 compatibility: 89 passed.
- Track 2C browser baseline: 2 passed.
- Frontend unit suite: 70 passed.
- Frontend production build: 2,196 modules transformed, 0 errors.
- Full backend unit suite: **2,182 passed, 2 skipped, 0 failed**, 2 dependency warnings.
- Integration suite: **5 passed, 0 failed**.
- Regression suite: **18 passed, 0 failed**.
- Existing accepted Track 2F browser suite: 8 passed.

### Checker gates

- Track 2C: Architecture PASS; Data Semantics PASS; QA PASS; Performance/UI PASS after one repair cycle.
- Track 2E: Architecture PASS; Quant/Data Semantics PASS; QA PASS after one repair cycle.
- Track 2G: Architecture PASS; Quant/Data Semantics PASS; QA PASS after one repair cycle.

## 14. Recommended Next Milestone

Do **not** begin Phase 11.

Recommended next milestone: **Track 2 data-quality remediation and sustained observation**, requiring:

1. A narrowly reviewed fix that prevents daily bars from satisfying intraday requests and persists exact bar-source timeframe provenance.
2. Continued read-only shadow collection with unchanged `research_v1` rules until lifecycle transitions and downstream snapshot coverage are observed naturally.
3. Human selection of the `QXOptionsScanner` target contract before any migration implementation.
4. A subsequent measurement-only baseline after the data-source fix; optimization proposals remain separate and human-approved.

This report stops at Track 2C/2E/2G completion. No Phase 11 behavior, broker write access, trading-rule changes, threshold changes, new vendor, cache architecture, queue, WebSocket, or destructive migration was introduced.
