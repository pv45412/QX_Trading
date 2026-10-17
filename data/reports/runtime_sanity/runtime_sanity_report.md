# QX Live Application Runtime Sanity Report

- Checked: 2026-09-17 00:16-00:22 America/New_York
- Overall result: **PARTIAL / RUNTIME DEFECTS FOUND**
- BE1 repair status: **PAUSED**. No BE1 or application code was changed.
- Services remain running for human review.

## Application Startup

| Service | URL | Status | Runtime |
|---|---|---|---|
| Frontend | `http://127.0.0.1:5174` | **RUNNING / HTTP 200** | Vite 6.4.3, process 15264, ready in 324 ms |
| Backend | `http://127.0.0.1:8510` | **RUNNING / HTTP 200** | Uvicorn process 22076; `/api/health` returned `{"status":"ok"}` |

The pre-existing backend process had been started before the current routers existed and returned `404` for System, Portfolio, and Opportunity routes. Both services were restarted from the current workspace. Fresh startup completed without warnings or errors.

## Schwab Health

The required commands were run:

- `.\.venv\Scripts\scanner.exe schwab-status`: configured, token present, access token valid, refresh token valid, OAuth restart not required.
- `.\.venv\Scripts\scanner.exe schwab-health`: PASS; Schwab auth and market data ready.
- `/api/system/schwab/test`: HTTP 200; `AUTHENTICATED`, refresh token `VALID`, provider `HEALTHY`.
- No credentials, secrets, access tokens, or refresh tokens are recorded in this report.

## Live Provider Tests

| Symbol | Quote | Intraday 5m bars | Options | Mapping |
|---|---|---|---|---|
| SPY | PASS, real-time Schwab response | **FAIL in application provider** | PASS, 150 calls + 150 puts | `SPY` |
| QQQ | PASS, real-time Schwab response | **FAIL in application provider** | PASS, 150 calls + 150 puts | `QQQ` |
| SPX | PASS, real-time Schwab response | **FAIL in application provider** | PASS, 330 calls + 330 puts | canonical `SPX` -> Schwab `$SPX` |

Schwab's raw price-history API returned candles for all three symbols. Each five-day response contained 390 rows but only 312 unique timestamps, with 78 duplicate timestamps and one non-increasing transition. `SchwabMarketDataProvider` therefore rejected every series with `ValueError: Schwab candle timestamps must be unique and ordered`. This is fail-closed behavior, but intraday retrieval is not operational for the application.

## Timestamps And Freshness

The check ran while the US regular session was closed. No freshness thresholds were changed.

| Symbol | Quote timestamp | Raw last 5m bar | Canonical bars `data_as_of` | Application freshness |
|---|---|---|---|---|
| SPY | 2026-09-17 00:00:00.060 UTC | 2026-09-16 19:55:00 UTC / 15:55 ET | UNAVAILABLE | Quote exceeds the configured 60-second threshold; raw bar is from the latest completed regular session, but provider validation fails and canonical bars are `INVALID/BLOCKED` (`TIMESTAMP_TIMEZONE_UNAVAILABLE`). |
| QQQ | 2026-09-16 23:59:59.948 UTC | 2026-09-16 19:55:00 UTC / 15:55 ET | UNAVAILABLE | Quote exceeds the configured 60-second threshold; raw bar is from the latest completed regular session, but provider validation fails and canonical 5m bars are `UNAVAILABLE/BLOCKED` (`REQUESTED_TIMEFRAME_UNAVAILABLE`). |
| SPX | 2026-09-16 20:31:33.308 UTC | 2026-09-16 19:55:00 UTC / 15:55 ET | UNAVAILABLE | Quote exceeds the configured 60-second threshold; raw bar is from the latest completed regular session, but provider validation fails and canonical 5m bars are `UNAVAILABLE/BLOCKED` (`REQUESTED_TIMEFRAME_UNAVAILABLE`). |

Canonical option snapshots were source-backed and synchronized but correctly labeled `STALE`: SPY `2026-09-16T20:15:01.022Z`, QQQ `2026-09-16T20:15:00.180Z`, and SPX `2026-09-16T20:59:59.997Z`. Current canonical 5m freshness therefore **cannot be confirmed**.

## Page Results

### System — PARTIAL

- Schwab visible as `CONFIGURED`, `AUTHENTICATED`, refresh token `VALID`, and Market API `HEALTHY`.
- Canonical pipeline visible as `core_v1`; rules metadata `AVAILABLE`.
- Bar cache `AVAILABLE` with 3,237 files and 1,563 symbols, but freshness is truthfully `UNVERIFIED`.
- Overall System state is `DEGRADED` because process-memory verification is unavailable.
- The System workspace does not expose an explicit Opportunity-service status tile.

### Today — PARTIAL

- Market Pulse renders.
- SPY and QQQ canonical cards render `BLOCKED`; SPX renders `UNAVAILABLE`.
- Legacy market movers render separately as `LEGACY SOURCE`.
- Canonical Opportunities incorrectly appear as `NO CURRENT QUALIFYING OPPORTUNITIES` rather than unavailable because the BE1 route returns HTTP 200 with an empty LIVE envelope.

### Opportunities — PARTIAL / BE1 BLOCKER VISIBLE

- No canonical rows are fabricated: 0 visible / 0 loaded.
- Legacy rows remain clearly labeled `LEGACY SOURCE`.
- Legacy data is dated 2026-09-11 and is not current-session evidence.
- Expected `CANONICAL DATA UNAVAILABLE` is not shown. The BE1 endpoint returns HTTP 200, `source_mode: LIVE`, with an empty list despite BE1 being `HUMAN_REQUIRED`. This is the known migration-ledger fail-open blocker and is distinct from Schwab health.

### Trade — BLOCKED, TRUTHFUL

- Live, non-fixture evaluations were requested for SPY, QQQ, and SPX.
- All endpoints returned HTTP 200 with `publication_state: BLOCKED` and lifecycle `BLOCKED`.
- Structure, regime, direction, trigger, invalidation, tradeability, options expression, and portfolio result remain unavailable because bars fail first; no downstream values are fabricated.
- Market Driver remains `UNAVAILABLE`.
- Execution Readiness remains `NOT ENABLED`.
- Direct Schwab quotes and option-chain calls work, but usable canonical intraday bars do not.

### Portfolio — PARTIAL / READ-ONLY

- Fresh Schwab read-only snapshot loaded with a masked `qxacct_...` identity and seven positions.
- Position symbols present: SOXL, NVDA, two FTNT option legs, two CMCSA option legs, and one UPS option leg.
- Phase 10 panel is present but has no linked candidate because Trade evaluations are blocked.
- Sync is `PARTIAL`; sector evidence, Greeks, and some P/L evidence are unavailable.
- No broker order-entry or broker-write controls are present.

### Research — PASS WITH SOURCE CAVEATS

All six modes render without browser exceptions:

1. Symbol: source-backed SPY snapshot; data as of 2026-09-15.
2. ETF / Sector: source-backed cached XLK relative-strength and constituent sections; freshness explicitly unverified.
3. Relative Strength / Rotation: source-backed cached analytics; freshness explicitly unverified.
4. Options / Strategy: renders, explicitly labeled `MODELED`, `LEGACY`, `SIMULATED / RESEARCH ONLY`, not live canonical Phase 9.
5. Historical / Backtest: source-backed historical snapshot renders; backtest remains user-triggered and simulated.
6. Long-Term: source-backed historical context renders; thesis input is local-session and not persisted.

## Runtime Errors And Separation Of Concerns

- Browser: zero uncaught page errors, zero failed network requests, and no application console errors across captured routes.
- Backend: no warnings, tracebacks, or errors in the fresh startup/runtime log.
- Frontend: no Vite stderr output.
- **Schwab/auth health is PASS.** Quote and option-chain APIs work, including SPX -> `$SPX` mapping.
- **Intraday application consumption is FAIL.** Raw candles exist but fail duplicate/order validation.
- **BE1 Opportunity health is a separate FAIL.** The route presents an empty LIVE response rather than unavailable because the known ledger-DDL drift blocker remains unresolved.
- No repair was attempted.

## Screenshots

- `screenshots/01-system.png`
- `screenshots/01b-system-providers.png`
- `screenshots/01c-system-data.png`
- `screenshots/02-today.png`
- `screenshots/03-opportunities.png`
- `screenshots/04-trade-spy.png`
- `screenshots/05-trade-qqq.png`
- `screenshots/06-trade-spx.png`
- `screenshots/07-portfolio.png`
- `screenshots/08a-research-symbol.png`
- `screenshots/08b-research-etf-sector.png`
- `screenshots/08c-research-relative-strength.png`
- `screenshots/08d-research-options-strategy.png`
- `screenshots/08e-research-historical.png`
- `screenshots/08f-research-long-term.png`
