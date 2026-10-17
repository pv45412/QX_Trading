# BE1 Migration Evidence

## Authoritative Database

- Typed setting: `Settings.runtime_database_path`.
- Default: `data/scanner_history.db`.
- The existing canonical runtime SQLite database is reused; no BE1-specific database exists.

## Applied Migrations

| Migration | SHA-256 checksum |
|---|---|
| `000_qx_schema_migrations` | `0a648ce2c21fea0bb1ea24fa2c9b1a0d67bdd2f41d242823c4212c4e71da42d0` |
| `001_be1_opportunity_v1` | `ad039e456ae1cd41c0bc7f1bb917bb42271720750ec23fe1063fd9d341d57611` |

Read-only inspection of `data/scanner_history.db` confirmed both matching ledger rows and these objects:

- `opportunity_publication_commands`
- `opportunity_evaluations`
- `idx_opportunity_current_query`
- `idx_opportunity_stream_query`

No opportunity records were manufactured or backfilled during migration.

## Proven Behavior

- Clean migration creates migration 000 with strict `CREATE TABLE`, then migration 001.
- A matching recorded checksum is an idempotent no-op.
- A checksum mismatch fails closed.
- An existing unledgered target object fails closed as schema drift.
- A ledger without migration-000 proof fails closed.
- Existing object SQL is compared with the exact normalized migration SQL.

Evidence tests: `tests/unit/test_be1_opportunities.py`.

## Application Fail-Closed Boundary

- Application construction mounts the canonical Opportunity router only after `OpportunityRepository.initialize()` validates the migration ledger, checksums, schema, tables, and indexes.
- Missing runtime stores remain non-creating and return `503` through an unavailable router.
- Checksum or schema drift returns sanitized `503 OPPORTUNITY_STORE_SCHEMA_INVALID` and never invokes opportunity row reads.
- A store restored to the approved checksum/schema and revalidated through `apply_opportunity_migrations()` can mount the canonical router again.
- Evidence tests: `tests/unit/test_be1_opportunity_api.py`.
