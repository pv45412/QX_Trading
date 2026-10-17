# BE1 API Contract

## Principles

- Read endpoints never execute `run_pipeline()`.
- Browsers cannot select observation mode; production queries are LIVE-only.
- Responses preserve null, zero, false, timestamps, states, and reason codes.
- Legacy discovery remains a separately labeled source.

## List Endpoint

```http
GET /api/v2/qx/opportunities
```

| Parameter | Rule |
|---|---|
| `symbols` | Optional bounded allowlist |
| `timeframe` | Optional exact canonical timeframe |
| `states` | Optional repeated lifecycle filter |
| `publication_states` | Optional repeated exact filter |
| `evaluated_after` | Optional UTC lower bound |
| `evaluated_before` | Optional UTC upper bound |
| `knowledge_as_of` | Optional persistence visibility ceiling |
| `include_terminal` | Default false |
| `include_blocked` | Explicit boolean; default policy requires approval |
| `fresh_only` | Default true |
| `limit` | Default 25; hard maximum 100 |
| `cursor` | Opaque versioned ordering cursor |

Horizon is not a canonical filter until BE2. Explicit `horizon_context` may be echoed with `context_only=true`.

```json
{
  "schema_version": "qx.opportunity-list.v1",
  "pipeline_version": "core_v1",
  "generated_at": "UTC timestamp",
  "query_as_of": "UTC timestamp",
  "source_mode": "LIVE",
  "items": [],
  "next_cursor": null,
  "has_more": false
}
```

Each item includes explicit `source_mode`, evaluation identity, symbol/timeframe, context-only horizon, evaluation timestamp, visibility, publication/lifecycle states, direction, primary playbook, trigger/invalidation, tradeability/options/portfolio summaries, evidence coverage, reasons, and dependency freshness. Normal Today and Opportunities reads accept only item-level `source_mode=LIVE`; response-level metadata is not inherited into items.

`include_blocked=true` includes a latest stream head whose lifecycle or publication state is `BLOCKED` without also requiring `include_terminal=true`. `include_terminal=true` independently enables non-blocked terminal lifecycle states such as `EXPIRED`, `NO_SETUP`, `NOT_TRADEABLE`, `OPTIONS_NOT_SUITABLE`, and `PORTFOLIO_VETOED`.

## Detail Endpoint

```http
GET /api/v2/qx/opportunities/{evaluation_id}
```

Returns the exact immutable safe decision projection required by Trade and WHY. It never returns raw source snapshots or sensitive portfolio data.

- `200`: exact record found.
- `404`: unknown identity; Trade renders unavailable and does not recompute.
- `409`: stored schema or integrity conflict cannot be served safely.
- `410`: archived record exists but is offline; only after archive approval.
- `422`: malformed identity or cursor.
- `503`: read store unavailable; no fallback to legacy or pipeline evaluation.

## Existing Evaluation Endpoint

```http
POST /api/v2/qx/evaluate/{symbol}
```

This remains the canonical evaluation command. Interactive calls are RESEARCH and are not written to the LIVE opportunity store. They return no persisted `evaluation_id`. Only a separately approved internal publisher may reserve a LIVE publication command and return a persisted identity.

## Consumer Rules

### Today

- Requests a bounded current LIVE list for attention states.
- Makes no per-opportunity evaluation calls.
- Keeps market-pulse ownership separate until an approved context contract exists.

### Opportunities

- Uses the same list endpoint with server-side filters and cursor pagination.
- Never maps legacy movers into canonical lifecycle rows.
- Shows empty, unavailable, blocked, stale, and terminal states explicitly.

### Trade

- With `evaluation_id`: one detail GET and zero evaluation POSTs.
- Validates symbol, timeframe, timestamp, pipeline version, and ID.
- Missing/mismatched identity fails visibly.
- Explicit reevaluation is a separate RESEARCH action. It returns an ephemeral result without a persisted opportunity ID and is clearly distinguished from the stored evaluation being viewed.

## Ordering and Cursor

Stable list order:

```text
evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
```

The cursor encodes the final tuple and schema version. Offset pagination is prohibited because concurrent inserts can shift pages.

## Caching

- Detail and list responses use strong ETags only when hashing the exact deterministic canonical response bytes before HTTP compression.
- Query filters, ordering, pagination, and representation/schema version are therefore part of the hashed representation.
- `result_sha256` is an integrity hash for the safe decision projection and is never substituted for a strong HTTP representation ETag.
- No new cache infrastructure is part of BE1.

## Default Publication Matrix

| Publication state | Default current list | Explicit audit/filter | Label |
|---|---|---|---|
| VERIFIED | Yes when lifecycle is progressive and record is current | Yes | VERIFIED |
| RESEARCH_ONLY | Yes when lifecycle is progressive and record is current | Yes | RESEARCH ONLY / NO EXECUTION |
| SIMULATED | No | Internal audit only | SIMULATED |
| BLOCKED | No | Yes through explicit blocked filter | BLOCKED |

Terminal lifecycle states are excluded by default regardless of publication state. The API never upgrades RESEARCH_ONLY to VERIFIED.
