# Today Live Quote Contract

## Scope

Expose and render truthful source-backed quote data for SPY, QQQ, and SPX on Today. Do not change BE1, opportunity logic, trading rules, or freshness thresholds.

## Backend Contract

`GET /api/v2/market/quote/{symbol}` supports SPY, QQQ, and SPX and returns:

- canonical symbol and provider-resolved symbol
- actual provider name
- last, bid, ask, change percentage, and volume without fallback fabrication
- quote and trade timestamps
- provider realtime flag
- retrieval timestamp, age in seconds, and strict freshness status

SPX must resolve to Schwab `$SPX`. Provider failures return an unavailable response; they must not invent values.

## Today Acceptance

Each Market Pulse card visibly shows:

- last price and change
- bid and ask where supplied
- source and realtime/delayed status
- quote timestamp and strict freshness
- canonical bar source, bar `data_as_of`, and bar freshness
- existing direction, regime, volatility, and session

The UI must not label a card simply AVAILABLE when neither a quote nor canonical bar provenance is visible.

## Verification

- backend contract tests cover Schwab values, SPX mapping, stale threshold, and unavailable provider behavior
- frontend tests require quote and bar provenance fields
- live browser check requires visible numeric values for SPY, QQQ, and SPX plus `SCHWAB`
