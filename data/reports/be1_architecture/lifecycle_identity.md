# Lifecycle and Identity

## Three Separate Identities

1. **Evaluation identity**: immutable `evaluation_id`; one completed invocation.
2. **Stream identity**: query grouping by environment, LIVE mode, symbol, timeframe, pipeline version, and config version.
3. **Setup identity**: not defined by BE1; accepted only if a canonical phase later emits a stable cross-evaluation identifier.

Conflating these identities is prohibited.

## Timeline Behavior

```text
09:35 WATCH               evaluation A
09:40 ARMED               evaluation B
09:45 TRIGGERED           evaluation C
09:50 OPTIONS_SUITABLE    evaluation D
09:55 PORTFOLIO_APPROVED  evaluation E
10:00 EXPIRED             evaluation F
```

Each row is the final state reached by one `run_pipeline()` call. Intermediate stage outputs remain inside that record and are not separate records.

## Repeated Evaluation Rules

- Retry with same idempotency key and same digests: no duplicate.
- Retry with same key and different digest: hard conflict.
- Approved LIVE producer reevaluation: new key and new record.
- Interactive Trade reevaluation: ephemeral RESEARCH result with no LIVE identity.
- Corrected observation: new record with `supersedes_evaluation_id`.
- Older late-arriving observation: retained but never selected as newest merely because it was recorded later.

## Terminal States

BLOCKED, NO_SETUP, NOT_TRADEABLE, OPTIONS_NOT_SUITABLE, PORTFOLIO_VETOED, and EXPIRED are immutable observations. They do not mutate or permanently close a symbol/timeframe stream. BE1 also preserves any current upstream ambiguity verbatim; it does not repair Phase 3-10 semantics.

## Freshness and Expiry

- Dependency freshness is copied from canonical provenance.
- Record age is service metadata.
- `expires_at` controls list visibility only.
- Derived visibility is CURRENT, STALE, ARCHIVED, or UNDATED.
- Lifecycle EXPIRED is never synthesized from service age.
- Missing approved expiry fails closed for fresh lists but detail-by-ID remains available.
- Historical visibility requires both `evaluation_timestamp <= market_as_of` and `recorded_at <= knowledge_as_of`.

## Horizon

The current pipeline owns timeframe, not DAY/SWING/INVEST horizon. BE1 stores only explicitly supplied `horizon_context`, labels it context-only, and excludes it from evaluation identity. BE2 owns future multi-timeframe semantics.

## Mode Isolation

| Mode | Producer | Persistence | Live API |
|---|---|---|---|
| LIVE | Approved internal publisher | opportunity table | Yes |
| SHADOW | Existing shadow adapter | `shadow_telemetry` | No |
| REPLAY | HistoricalReplayAdapter | `replay_*` | No |
| RESEARCH | Interactive/ad hoc evaluation | none or isolated future store | No |
| FIXTURE | Tests/previews | never production storage | No |

## Exact Trade Handoff

The URL carries evaluation ID, symbol, timeframe, and evaluation timestamp. Trade retrieves by ID and validates duplicated context. A mismatch is an explicit identity error. Trade must not substitute the newest stream record or invoke evaluation as a hidden fallback.
