# BE1 Rollback Evidence

## Compatibility Rollback

BE1 is additive. A code rollback removes the opportunity router, publisher, repository usage, and frontend read adapters while leaving the existing canonical v2 evaluation, shadow, replay, snapshot, legacy discovery, and UI routes unchanged.

## Data Rollback

No destructive down migration is authorized. The two BE1 tables and migration ledger rows remain dormant if the feature code is rolled back. This preserves immutable audit evidence and avoids unsafe schema deletion.

## Failure Isolation

- Missing runtime database: read-only app construction does not create it; the opportunity API returns unavailable while existing routes continue.
- Corrupt or drifted schema: opportunity migration initialization fails closed and logs only the exception type; legacy read routes retain their existing sanitized handling.
- Opportunity read failure: no fallback to legacy data and no pipeline recomputation.
- Missing detail identity: Trade displays unavailable and never silently POSTs a new evaluation.

## Verification

- Existing API compatibility suite passed after migration initialization was made non-invasive.
- Interactive `/api/v2/qx/evaluate/{symbol}` remains RESEARCH and creates zero LIVE opportunity rows.
- Legacy discovery remains separately labeled and routable.

## Fail-Closed Repair Rollback

Rolling back this repair would reintroduce the prohibited behavior where migration failure is logged but the trusted router is still mounted. The safe operational rollback is therefore to retain the validation-gated router selection or disable the Opportunity routes entirely; no data migration or schema deletion is involved.
