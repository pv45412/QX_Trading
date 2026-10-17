# Opportunity Domain Model

## Aggregate Boundary

`OpportunityRecord` is an immutable record of one completed canonical evaluation. It is a persistence/query projection, not a trading-engine replacement.

## Proposed Record

| Field | Type | Rule |
|---|---|---|
| `schema_version` | literal `qx.opportunity.v1` | Contract version |
| `evaluation_id` | opaque string | Server-issued immutable identity |
| `idempotency_key` | string | Unique producer retry boundary |
| `observation_mode` | enum | LIVE in the live repository |
| `environment_id` | string | Non-secret deployment namespace |
| `producer_id` | string | Approved internal producer |
| `producer_run_id` | string | Stable internal run/batch identifier |
| `symbol` | string | Uppercase canonical symbol |
| `timeframe` | string | Copied from result |
| `horizon_context` | nullable string | Explicit product context only; never inferred |
| `evaluation_timestamp` | UTC datetime | Canonical point-in-time T |
| `request_started_at` | nullable UTC datetime | Copied from result |
| `recorded_at` | UTC datetime | Persistence knowledge time |
| `expires_at` | nullable UTC datetime | Service visibility only |
| `freshness_policy_version` | nullable string | Approved visibility policy |
| `publication_state` | PublicationState | Copied verbatim |
| `lifecycle_state` | LifecycleState | Copied verbatim |
| `pipeline_version` | string | Copied verbatim |
| `config_version` | string | Copied verbatim |
| `engine_versions` | map | Copied verbatim |
| `primary_playbook_id` | nullable string | Canonical reference only |
| `source_setup_reference` | nullable string | Only if emitted canonically |
| `reason_codes` | list | Ordered canonical codes |
| `evidence_summary` | list | Canonical summary |
| `evidence_coverage` | nullable number | Copied; never recalculated |
| `coverage_status` | nullable string | Copied |
| `data_dependencies` | map | Allowlisted point-in-time provenance |
| `decision_payload` | object | Safe versioned consumer projection |
| `input_fingerprint` | string | Hash of visible canonical input manifest |
| `bar_window_sha256` | string | Hash of exact ordered visible bars passed to the pipeline |
| `result_sha256` | string | Hash of safe semantic projection |
| `stream_key` | string | Query lineage key, not record identity |
| `supersedes_evaluation_id` | nullable string | Explicit correction lineage |

## Identity Rules

- `evaluation_id` uniquely identifies the persisted invocation.
- `idempotency_key` uniquely identifies a producer attempt and is never client-controlled.
- `evaluation_id` uses `qxev1_<UUIDv7 lowercase hex>` and is generated only after a new command reservation succeeds.
- `idempotency_key` uses `qxcmd1_<SHA-256>` over RFC 8785 JSON containing schema version, environment ID, producer ID, producer run ID, uppercase symbol, and canonical timeframe.
- Live `evaluation_timestamp` is deliberately excluded from command identity because it is established only after required provider acquisition; it enters the later input fingerprint.
- Same key plus same digests returns the existing record.
- Same key plus different digest is an integrity conflict.
- Intentional reevaluation uses a new key and creates a new ID.
- The key is reserved before provider acquisition and pipeline execution.
- Runtime latency, request start, and record time do not enter input/result fingerprints.

## Invariants

- One record equals one evaluation.
- Records are immutable after insert.
- Lifecycle and publication values are copied, never inferred.
- Observation mode and publication state are independent.
- LIVE repository writes reject non-LIVE modes.
- Missing values remain null; zero, false, and empty string remain distinct.
- Raw broker account numbers and OAuth/security material are prohibited.
- Any account reference must use an internal `qxacct_*` identifier.
- Portfolio projection excludes account equity, buying power, positions, and unrestricted related-symbol lists.

## Stream Identity

Recommended stream key preimage:

```text
environment_id | observation_mode | symbol | timeframe | pipeline_version | config_version
```

Horizon is excluded because BE1 cannot define multi-timeframe semantics. A stream orders evaluations; it does not prove a shared setup lifecycle.

## State Categories

- Progressive observations: WATCH, ARMED, TRIGGERED, TRADEABLE, OPTIONS_SUITABLE, PORTFOLIO_APPROVED.
- Stop observations: BLOCKED, NO_SETUP, NOT_TRADEABLE, OPTIONS_NOT_SUITABLE, PORTFOLIO_VETOED, EXPIRED.

These categories are query conveniences only and never rewrite canonical state.

## Safe Decision Projection

Store only fields required by Today, Opportunities, Trade, and WHY:

- structure/regime/direction summaries and safe evidence
- primary playbook and canonical rule results
- trigger and invalidation evidence
- tradeability state and reasons
- options suitability and candidate summary
- portfolio state, binding constraint, and approved reason codes
- stage availability/latency and versions
- dependency provenance and safe snapshot references

Reference, rather than duplicate, raw bars, raw option chains, account snapshots, and provider payloads.

## Canonical Bar-Window Digest

Before `run_pipeline()`, normalize the exact visible bars in ascending timestamp order. Hash the timeframe plus every bar timestamp and canonical OHLCV value using a versioned serialization. Store the digest, bar count, first/last timestamp, and source provenance in the input manifest. Changed cache content with the same `data_as_of` therefore produces a different fingerprint.

The audited bar source must also expose a validated cache-content SHA-256 and source retrieval timestamp from its provenance sidecar. Files without valid retrieval provenance may support RESEARCH evaluation but cannot produce a LIVE OpportunityRecord.

## Canonical Encoding

- Hash manifests use UTF-8 RFC 8785 JSON canonicalization.
- Timestamps are normalized to UTC ISO 8601 with `Z` and microsecond precision.
- Symbols are uppercase and timeframes use canonical spellings.
- Non-finite numbers are rejected.
- Ordered evidence/rule arrays remain ordered; map keys are lexicographically sorted by canonical JSON.
- `input_fingerprint` hashes `qx.opportunity-input.v1`, environment, producer, symbol, timeframe, evaluation timestamp, bar-window manifest, option/account snapshot visibility references, and pipeline/config versions.
- `result_sha256` hashes `qx.opportunity-decision.v1` and the exact safe decision projection.
- Operational timestamps, latency measurements, database IDs, and presentation-only horizon context are excluded from both hashes.

## OpportunityDecisionV1

The detail DTO is a field-level allowlist, not an arbitrary object:

- Root: symbol, timeframe, evaluation/request timestamps, publication/lifecycle state, reason codes, evidence summary, pipeline/config/engine versions, stage latency, dependency provenance.
- Structure: regime, score, latest BOS/CHoCH/event, protected levels, event/knowledge timestamps, canonical source IDs.
- Regime: trend, volatility, gamma, session, reasons/evidence, config and engine version.
- Direction: label, score, evidence coverage, coverage status, ordered factor records.
- Playbook: ID/version/state/direction, setup flag, reason, trigger/invalidation definitions and prices, structural targets, rule results, event/knowledge timestamps.
- Trigger: canonical setup reference, state, prices, timestamps, source validity, trigger event, rule results, reasons/evidence.
- Tradeability: IDs, state, prices, participation/coverage, structural risk-reward, target candidates, reasons/evidence, timestamps, publication/config/engine versions.
- Options: expression/playbook IDs, state, safe candidate summaries, primary candidate ID, data-as-of, reasons/evidence, publication/config/engine versions; no raw option chain.
- Portfolio: risk/expression/candidate IDs, state, symbol/strategy/direction, binding constraint, approved contract cap, reasons/evidence, evaluated/data-as-of/config/engine versions.

Portfolio fields explicitly excluded: account ID, equity, buying power, positions, related symbols, Greek/exposure totals, daily-loss values, and raw account evidence. RuleResult projections preserve rule ID/version, category, required/observed value, passed, severity, hard gate, weight, contribution, source, event/knowledge timestamps, and detail without normalization.
