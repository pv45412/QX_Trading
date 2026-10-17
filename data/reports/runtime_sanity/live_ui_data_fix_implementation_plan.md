# Live Canonical Bar Timestamp Fix Plan

## Technical Goal

Restore live SPY, QQQ, and SPX canonical evaluations by correcting the Schwab intraday request boundary and passing live normalized bars through the existing point-in-time quality policy.

## Requirements

- Preserve UTC-aware evaluation timestamps and bar timestamps.
- Preserve duplicate, order, OHLCV, session, cadence, stale-data, future-bar, and incomplete-candle rejection.
- Use live Schwab bars only for requests without an explicit historical `evaluation_timestamp`.
- Keep explicit point-in-time/historical evaluations cache-backed.
- Do not alter trading rules, lifecycle rules, thresholds, BE1, or execution behavior.

## Component Impact

- `src/qx/brokers/schwab/market_data.py`: remove the request parameter proven to duplicate the latest session.
- `src/qx/pipeline/market_data_quality.py`: expose the existing audit policy for an already-normalized in-memory bar frame.
- `src/qx/interfaces/qx_v2.py`: acquire and audit live bars for live evaluations; retain cache loading for historical evaluations and provider failure fallback.
- `src/qx/interfaces/web.py`: inject the configured Schwab market-data provider into the canonical router.
- Focused provider, quality, API, and UI tests only.

## Data And API Contracts

- No response-schema change.
- Bar dependency provenance changes from stale/missing local cache to the configured live provider when live acquisition passes validation.
- `data_as_of` remains the newest completed bar at or before the UTC evaluation timestamp.

## Risks And Edge Cases

- Duplicate or out-of-order provider data must remain blocked, never deduplicated or reordered.
- An in-progress candle must remain excluded.
- Off-session, missing-interval, cadence-mismatch, stale, future, invalid OHLCV, or naive timestamps must remain blocked.
- Historical requests must not reach the live provider.
- Provider failures must fail closed through the existing cache audit rather than fabricate bars.

## Authorization

The user explicitly authorized this timestamp/data-normalization repair after proof and prohibited BE1 or trading-rule changes.
