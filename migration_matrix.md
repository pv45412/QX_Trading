# QX Track 2G Legacy Migration Readiness

Status: **OBSERVATION ONLY — NO DESTRUCTIVE MIGRATION APPROVED**  
Canonical pipeline version: `core_v1`

## Classification Rules

- `KEEP`: canonical or still-authoritative capability.
- `ADAPT`: retain the capability but move its input/output boundary toward canonical contracts.
- `REPLACE`: move consumers to an existing canonical implementation before deprecation.
- `DEPRECATE`: freeze new consumers and keep only for compatibility or shadow comparison.
- `REMOVE_LATER`: eligible only after every listed dependency, test, and rollback gate passes with human approval.

## Migration Inventory

| Candidate | Classification | Current consumers | Canonical replacement | Migration risk | Required tests | Rollback strategy |
|---|---|---|---|---|---|---|
| `src/qx/pipeline/` | KEEP | `/api/v2/qx/evaluate/{symbol}`, replay, V1 shadow comparison, lifecycle UI | Same canonical `run_pipeline()` | High if orchestration forks or legacy imports leak in | Track 1 integration, provider causality, replay, full unit | Revert only additive adapters; preserve `core_v1` entry point |
| `src/qx/interfaces/qx_v2.py` | KEEP | `web/src/qx-v2-client.js`, benchmark and shadow observation runners | Same V2 route | High; point-in-time or provider failures could misstate availability | V2 API compatibility, provider visibility, timestamp causality | Disable frontend feature flag and retain V1 route |
| `web/src/qx-v2-*`, `web/src/QXLifecyclePanel.jsx`, `web/src/useQxV2Evaluation.js` | KEEP | `QXTradingSuite`, isolated preview and browser tests | Same thin V2 adapter and lifecycle component | Medium; presentation drift or duplicate requests | Adapter unit, fixture unit, Track 2F browser, build | Turn off `qx_v2_ui_enabled`; V1 screens remain intact |
| `src/qx/options_scanner/services/signal_service.py` | DEPRECATE | `/api/options-scanner/scan`, V1 integration/unit tests, shadow comparison | `qx.pipeline.orchestrator.run_pipeline()` through V2 | High; V1 returns synthetic option-chain semantics and a different result contract | V1 compatibility, V1 fail-open shadow, V2 lifecycle/API tests | Keep V1 route and module enabled while V2 remains feature flagged |
| `src/qx/options_scanner/services/direction_service.py` | REPLACE | Legacy `SignalService`, options-scanner tests | `src/qx/direction/direction_engine.py` via canonical pipeline | High; labels, evidence coverage, weights, and freshness differ | Direction characterization, shadow disagreement, consumer contract | Restore legacy service for V1 only; never import it into V2 |
| `src/qx/options_scanner/services/regime.py` | DEPRECATE | No runtime or test imports found; only the unreferenced `RegimeService` definition remains | `src/qx/regime/market_regime.py` via canonical pipeline if a future consumer needs regime output | Low now, but removal still requires a verified import scan and human approval | Import scan, package export checks, full unit | Restore the file if an external consumer not represented in this repository is identified |
| `src/qx/options_scanner/services/strategy_selector.py` and `trade_constructor.py` | REPLACE | Legacy `SignalService`, scanner tests | Phase 6 playbooks plus Phase 9 `OptionsExpressionEngine` | High; strategy naming and construction semantics are not one-to-one | Playbook, options-expression, adapter, shadow comparison | Continue returning V1 strategy objects until consumers migrate |
| `src/qx/options_scanner/services/risk_service.py`, `veto_service.py`, `position_sizer.py`, `trade_scorer.py` | ADAPT | Legacy scanner; parts of `src/qx/execution/pipeline.py`; tests | Phase 8 `TradeabilityEngine` and Phase 10 `PortfolioRiskEngine` for canonical evaluation | Critical; legacy sizing/execution concepts exceed Track 2 scope | Tradeability, portfolio risk, V1 compatibility, future Phase 11 safety | Preserve modules unchanged and keep execution disconnected from V2 |
| `src/qx/options_scanner/services/telemetry.py` | DEPRECATE | `tests/options_scanner/test_signal_pipeline.py`; no production route imports it | Dedicated `src/qx/pipeline/shadow_telemetry.py` covers canonical comparison only; no replacement is required until a production consumer exists | Low; file-based V1 snapshots are a different schema from canonical shadow rows | Import scan, legacy scanner telemetry test, full unit | Retain the file and its JSON snapshot format |
| `src/qx/telemetry/` | ADAPT | `/api/telemetry/signals`, integration/unit tests, strategy telemetry | Keep for legacy signal audit; define a separate read adapter if canonical shadow/replay analytics must be presented together | Medium; signal audit records and canonical comparison rows have different purposes | Telemetry service, API integration, bounded-query and mixed-store presentation tests | Keep `/api/telemetry/signals` on the current store |
| `/api/options-scanner/scan` in `src/qx/interfaces/web.py` | DEPRECATE | `web/src/QXOptionsScanner.jsx`, integration/regression tests | `/api/v2/qx/evaluate/{symbol}` | High; POST payload and V1 response differ from V2 lifecycle | Endpoint contract, UI feature-flag, shadow persistence, fallback | Route remains active; frontend can switch back immediately |
| `/api/options-scanner/ideas` in `src/qx/interfaces/web.py` | ADAPT | `web/src/QXOptionsIdeas.jsx` | No direct canonical replacement yet; eventual read model from approved V2 outcomes | High; ideas are not equivalent to live canonical lifecycle states | Existing ideas API/UI tests plus future V2 read-model tests | Keep current read endpoint and storage |
| `src/qx/signals/smc_rules_engine.py` | DEPRECATE | `src/qx/market/ticker_service.py`, Phase 0/2 legacy tests | Phase 3–8 canonical pipeline outputs | High; legacy setup schema and rules differ | Characterization, ticker-service contract, canonical lifecycle parity | Keep legacy engine isolated while ticker service remains on it |
| `src/qx/signals/calibration.py` | ADAPT | Phase 3 signal-quality tests | Future research analytics over replay/shadow data; no automatic threshold updates | Medium; calibration must not mutate `research_v1` | Calibration unit plus human-approved research change tests | Keep read-only legacy calibration path |
| `src/qx/signals/freshness.py` and `validator.py` | ADAPT | `src/qx/execution/pipeline.py`, Phase 3 tests | Canonical dependency freshness and publication-state contracts, pending Phase 11 design | Critical; execution safety boundary | Existing execution safety and publication-state tests; future Phase 11 approval | Preserve current validators and deny V2 execution |
| `src/qx/market/regime.py` | REPLACE | watchlist engine, daily workflow report, Streamlit scan, SPX dashboard, futures snapshot | `src/qx/regime/market_regime.py` with an explicit compatibility adapter | High; legacy output is a dataclass/dataframe contract used broadly | Watchlist, reports, scan UI, SPX dashboard, regime characterization | Adapter can delegate back to legacy implementation behind a flag |
| `src/qx/market/ai_review.py` and `/api/ai/*` | ADAPT | `web/src/AIReview.jsx`, system control, evidence/review routes | Canonical V2 evidence as read-only input; no AI signal authority | High; AI review currently has separate evidence and must not influence V2 rules | AI evidence/review route tests, canonical isolation, prompt/output safety | Keep current read-only AI feature isolated from V2 |
| `web/src/QXOptionsScanner.jsx` | ADAPT / HUMAN_REQUIRED | Options Scanner workspace | Architecture decision not approved: either adapt the workflow around V2 lifecycle plus a future account-aware read model, or retain the distinct V1 scanner experience | High; current UI sends `account_equity`, expects strategy rankings, and fabricates fallback strategy data, while V2 accepts a symbol and returns lifecycle evidence | Contract decision record, removal of fabricated fallback data, browser loading/error/state tests, V1/V2 rollback test | Keep the V1 component and route unchanged until a human selects the target contract |
| `web/src/QXOptionsIdeas.jsx` | ADAPT | Options Ideas workspace | Future canonical read model; none approved in Track 2 | Medium; no canonical ideas/history endpoint yet | Existing component tests plus future read-model contract | Keep current component and endpoint |
| `web/src/AIReview.jsx` | ADAPT | AI Review panel | Canonical evidence payload, still presentation-only | Medium; must not reintroduce AI signal logic into V2 | UI request/error tests and API isolation | Keep legacy evidence endpoint behind existing panel |
| `web/src/QXTradingSuite.jsx` | ADAPT | Main dashboard composition | Continue feature-flagged V2 lifecycle insertion, then migrate one consumer at a time | Medium; broad screen composition | Full frontend unit/build/browser regression | Disable V2 feature flag and retain existing screen composition |
| `src/qx/execution/` and `/api/execution/*` | ADAPT | Execution API and execution tests | **No Track 2 replacement. Phase 11 remains unapproved.** | Critical; broker/order effects | Existing execution safety tests; future broker-write approval and end-to-end controls | Keep V2 disconnected; preserve publication-state rejection gates |
| Legacy modules after all consumers move | REMOVE_LATER | None permitted before removal | Canonical paths listed above | Critical and destructive | Full unit/integration/browser, import scan, rollback drill, human approval | Restore tagged legacy release and re-enable old route/feature flag |

## Duplicate Calculations and Semantic Differences

| Domain | Legacy calculations | Canonical calculation | Material difference |
|---|---|---|---|
| Structure/setup | `signals/smc_rules_engine.py`, `market/structure/structure_engine.py` | `structure/smc_suite.py` plus playbooks | Legacy setup objects do not encode the full canonical lifecycle/evidence ladder. |
| Regime | `market/regime.py`, `options_scanner/services/regime.py`, internal legacy signal regime | `regime/market_regime.py` | Labels, inputs, freshness, gamma/session treatment, and output schemas differ. |
| Direction | options-scanner direction and legacy signal rules | `direction/direction_engine.py` | Canonical direction includes weighted evidence, provenance, coverage, and reason semantics. |
| Strategy/playbook | scanner strategy selector and trade constructor | Phase 6 playbooks and Phase 9 options expression | A legacy option strategy is not equivalent to a canonical playbook or suitability result. |
| Trade gate | scanner veto/risk/scorer | Phase 7 trigger plus Phase 8 tradeability | Canonical sequencing requires trigger confirmation before tradeability. |
| Portfolio risk | legacy account-equity sizing and execution pipeline | Phase 10 portfolio risk | Canonical hard gates require point-in-time read-only account and sector provenance. |
| Freshness | legacy freshness checker and route-local cache behavior | canonical dependency statuses and snapshot visibility | Canonical snapshots require both `data_as_of` and `retrieved_at` visibility; bar timeframe provenance still needs repair. |
| Telemetry | V1 signal JSONL/service telemetry | SQLite `shadow_telemetry`, replay stores, Track 2 analyses | Canonical telemetry preserves pipeline version, lifecycle, evidence/data quality, and stage latency. |

## API and UI Migration Order

1. Keep `/api/v2/qx/evaluate/{symbol}` and `core_v1` stable.
2. Repair and test bar-source timeframe provenance before enabling more intraday V2 UI traffic.
3. Keep shadow collection running long enough to observe non-zero lifecycle transitions without changing rules.
4. Add a canonical read model only where an existing UI requires data not represented by one evaluation.
5. Obtain human approval for the materially different `QXOptionsScanner` target contract before migration; retain instant V1 rollback.
6. Adapt AI review to consume canonical evidence without becoming a decision engine.
7. Migrate watchlist/report/SPX consumers through a tested regime compatibility adapter.
8. Freeze new imports of legacy signals/options-scanner calculation services.
9. Revisit execution only under separately approved Phase 11 governance.
10. Request human approval before any destructive module or route removal.

## Dependency Graph

```text
canonical provider/timeframe provenance
    -> stable /api/v2/qx/evaluate/{symbol}
        -> sustained shadow observations and semantic comparison
            -> HUMAN_REQUIRED frontend scanner contract decision
                -> approved frontend migration behind feature flag
                -> V1 /api/options-scanner/scan deprecation
                    -> SignalService consumer count reaches zero
                        -> options_scanner calculation modules eligible for REMOVE_LATER

canonical regime compatibility adapter
    -> watchlist engine
    -> daily workflow reports
    -> Streamlit scan
    -> SPX dashboard and futures snapshots
        -> src/qx/market/regime.py eligible for REMOVE_LATER

canonical lifecycle/read models
    -> ticker service migration
        -> src/qx/signals/smc_rules_engine.py eligible for REMOVE_LATER

legacy signal audit requirements
    -> decide whether qx.telemetry remains standalone or gains a read-only canonical adapter
        -> preserve /api/telemetry/signals compatibility
            -> options_scanner/services/telemetry.py import count remains zero
                -> file telemetry module eligible for REMOVE_LATER

future human-approved Phase 11 architecture
    -> execution freshness/validation replacement
    -> broker-write security approval
    -> execution API migration
        -> legacy execution dependencies eligible for REMOVE_LATER
```

## Removal Gates

A candidate is not safe to remove until all of the following are true:

1. Production import scan shows zero consumers.
2. Canonical replacement has contract, point-in-time, and rollback tests.
3. Shadow/replay evidence covers relevant states; low counts remain findings, not a reason to loosen rules.
4. Frontend/API consumers have a tested feature-flag rollback.
5. Full backend, integration, frontend, build, and browser suites pass.
6. Destructive migration receives explicit human approval.

Track 2G performs none of these removals.
