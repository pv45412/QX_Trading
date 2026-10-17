# QX Data Quality Remediation and Sustained Shadow Validation Plan

## Scope

This milestone remediates canonical market-data quality, reports provider health and
snapshot coverage, and only then permits sustained shadow observation. It does not
change Phase 3-10 trading logic, thresholds, playbooks, lifecycle semantics, or
execution behavior.

## Ordered Delivery

1. **DQ1 Market data quality**
   - Resolve cache files by exact requested timeframe class.
   - Audit raw bars before normalization for malformed, duplicate, and out-of-order data.
   - Enforce point-in-time visibility and exclude explicitly identified incomplete candles.
   - Validate exchange-session boundaries and expected completed-bar freshness.
   - Block canonical publication when required bars are stale, invalid, or unavailable.
   - Generate a `MarketDataQualityReport` for the approved symbols and timeframes.
2. **DQ2 Provider health and authentication**
   - Report `AUTHENTICATED`, `UNAUTHENTICATED`, `DEGRADED`, `STALE`, or `UNAVAILABLE`.
   - Preserve downstream `UNAVAILABLE` semantics without fabricating snapshots.
   - Stop for human action before any credential or security change.
3. **DQ3 Snapshot coverage**
   - Measure bars, quotes, options, and account coverage independently.
4. **DQ4 Sustained canonical shadow validation**
   - Run only after DQ1-DQ3 pass, through `run_pipeline()`, without execution.
5. **DQ5 Scarcity diagnostics**
   - Attribute lifecycle scarcity to evidence and gate reasons without rule changes.
6. **DQ6 Structure performance profile**
   - Measure function timings and workload counts without optimization.

## Safety and Validation

- Cache selection never falls back across intraday and daily timeframe classes.
- Every consumed bar satisfies `data_as_of <= evaluation_timestamp`.
- Stale or invalid required bars produce an explicit blocked dependency.
- Provider and snapshot absence remains explicit and is never replaced with synthetic data.
- QXOptionsScanner remains documentation-only and `HUMAN_REQUIRED` for replacement.
- Each completed workstream receives independent architecture, data/quant, QA, and
  performance review as applicable, with no more than three automated repair cycles.
- Phase 11, broker writes, threshold changes, new vendors, and destructive migrations
  remain out of scope.
