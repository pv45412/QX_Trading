# Track 2G Migration Readiness Result

- Status: `INVENTORY_COMPLETE_REMOVAL_NOT_READY`
- Mode: inventory and dependency analysis only
- Canonical pipeline: `core_v1`
- Legacy deletions: `0`
- Route removals: `0`
- Execution changes: `0`

The complete candidate inventory, consumer mapping, canonical replacements, risks, required tests, rollback strategies, semantic differences, and dependency graph are maintained in [`migration_matrix.md`](../../migration_matrix.md).

## Readiness Finding

Legacy removal is **not ready**. The highest-priority prerequisite is correcting and proving bar-source timeframe provenance before broader intraday V2 adoption. Sustained shadow evidence is also insufficient: the current approved observation batch contains only `NO_SETUP` and `BLOCKED` states, with zero lifecycle transitions. These are observations only and do not justify rule changes.

The `QXOptionsScanner` target contract is `HUMAN_REQUIRED`: its account-equity and ranked-strategy workflow is materially different from the symbol-only canonical lifecycle endpoint. Track 2G does not choose between adapting that workflow and retaining it as a separate experience.

## Safe Next Actions

1. Correct the intraday/daily cache-source ambiguity under a separately reviewed data-correctness task.
2. Continue non-executing shadow collection with unchanged trading rules.
3. Obtain human approval for the `QXOptionsScanner` target contract, then migrate one UI/API consumer at a time behind the existing V2 feature flag.
4. Build and test a compatibility adapter before replacing `src/qx/market/regime.py` consumers.
5. Keep `src/qx/execution/` disconnected from canonical V2 until Phase 11 receives human approval.

No candidate is approved for destructive removal in Track 2G.
