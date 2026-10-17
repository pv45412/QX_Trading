# BE1 Failure Modes

| Failure | Required behavior | Prohibited fallback |
|---|---|---|
| `run_pipeline()` fails | No record; surface evaluation failure | Partial/manufactured opportunity |
| Persistence unavailable | Mark result unpersisted; exclude from list | Claim retrievable identity |
| Duplicate retry | Return existing record | Insert duplicate |
| Reserved/indeterminate retry | Return reconciliation-required status | Rerun providers/pipeline automatically |
| Same key, different digest | Integrity conflict and rollback | Overwrite old payload |
| Corrected evaluation | New record with supersession link | Mutate prior record |
| Older evaluation arrives late | Retain for audit; preserve ordering | Replace newer record by arrival time |
| Unknown mode | Reject write | Default to LIVE |
| Browser supplies mode | Ignore/reject; API remains LIVE-only | Query shadow/replay |
| Raw account identifier detected | Reject and sanitize logs | Store or log the value |
| Missing dependency provenance | Fail closed | Mark fresh/verified |
| Invalid evaluation ID | 422 | Fuzzy lookup |
| Missing detail record | 404 and Trade unavailable | Silent reevaluation |
| Unsupported schema | 409 | Best-effort coercion |
| Stale service record | Exclude/label stale | Rewrite lifecycle to EXPIRED |
| Invalid cursor | 422 | Restart silently |
| Database busy | Bounded retry, then 503 | Unbounded wait or duplicate evaluation |
| Projection mismatch | Block write and alert safely | Drop unknown fields silently |
| Snapshot reference missing | Explicit provenance unavailable | Reconstruct from future/current data |
| Bar cache mutated with same timestamp | Different bar digest/input fingerprint | Treat inputs as identical |
| Consumer outage | Existing routes remain under rollback | Relabel legacy rows canonical |

## Isolation Rules

- Persistence is downstream and cannot alter the canonical result.
- Read failures invoke no providers or engines.
- Write failures cause no automatic second evaluation.
- Shadow/replay failures cannot populate live opportunities.
- Live store failures cannot fall back to fixtures or legacy discovery.
- Free-form exception text is not persisted in the opportunity DTO.

## Safe Observability

Logs may include operation, evaluation ID, symbol/timeframe, safe status/reason code, elapsed time, and duplicate outcome. Logs must exclude payload JSON, account identifiers, credentials, tokens, callback URLs, raw snapshots, and unrestricted provider errors.
