# Task Contract: OBS1B Real Live/Shadow Validation

- **task_id:** OBS1B
- **title:** Real Live/Shadow Validation Campaign
- **current state:** IN_PROGRESS

## Goal

Execute a sustained real-market observation campaign for the Market Driver Engine (`core_v1`) without modifying any trading rules or thresholds.
Collect a minimum of 5,000 authentic real-market observations across 8 symbols over 5–10 trading sessions to establish empirical driver stability, persistence, flip frequency, regime independence, and forward returns.

## Dependencies

- MD2 is COMPLETE.
- BE1 and BE2 are COMPLETE.
- Authenticated Schwab market data connector is ACTIVE.
- Synthetic sessions are strictly separated and NOT counted toward the target.

## In Scope

- Target universe: `SPY`, `QQQ`, `SPX`, `NVDA`, `AAPL`, `MSFT`, `AMD`, `TSLA`.
- Timeframe: 5m execution/setup timeframe with multi-timeframe context (1h HTF, Daily Macro).
- Canonical evaluation pipeline: `core_v1`.
- Mandatory metrics recorded per observation:
  - Symbol, evaluation timestamp, lifecycle state, regime, direction, HTF factor.
  - Market driver, driver strength, persistence state, confirming evidence, conflicting evidence.
  - Evidence coverage, missing sources, bar freshness.
  - Realized forward price movement ($t+1, t+3, t+6, t+12$ bars) calculated post-hoc.
- Analytics:
  - Primary & secondary driver distributions.
  - Availability & unavailable reason breakdowns.
  - Session flip frequency and persistence duration.
  - Cross-tabulation matrices: Driver vs Regime, Driver vs Direction, Driver vs Lifecycle, Driver vs Forward Continuation.
  - Coverage by evidence family.
  - Archetype reachability and observability across all 11 archetypes.
- UI visual audit:
  - Capture representative screenshots under `data/reports/obs1b_validation/ui/` demonstrating available, unavailable, conflicting, and partial coverage states.

## Out of Scope

- Changes to thresholds (35 primary, 20 secondary, 10 hysteresis).
- Changes to coverage rules (3/5 contract: underlying + index + sector/delta/gamma).
- Changes to archetype logic or scoring formulas.
- Broker writes, order placement, or Phase 11 execution.
- Starting PERF2 before formal acceptance.

## Acceptance Criteria

- Minimum 5,000 authentic `LIVE` / `SHADOW` observations across the 8 symbols.
- Zero synthetic observations counted toward the sustained validation total.
- Zero point-in-time / lookahead violations.
- Full maintained unit suite passes 100% green.
- Telemetry dataset committed to `data/reports/obs1b_validation/obs1b_real_shadow_telemetry.json`.
- Comprehensive report committed to `data/reports/obs1b_validation/OBS1B_REAL_OBSERVATION_REPORT.md`.
