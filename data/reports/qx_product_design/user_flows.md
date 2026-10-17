# QX Target User Flows

## Shared Flow Rules

- `DAY`, `SWING`, and `INVEST` are horizon filters carried through navigation.
- Symbol, timeframe, evaluation timestamp, and selected account are explicit context.
- Opportunities discovers; Trade Workspace decides; Portfolio constrains; Research
  explains.
- Canonical lifecycle state always comes from the V2 `core_v1` evaluation. The browser
  does not synthesize, promote, or rename states.
- Missing downstream data is shown as `UNAVAILABLE` or `SKIPPED`; upstream analysis
  remains visible.
- No flow in this milestone submits, stages, simulates, or promises an order.

## Day Trader

```text
Today [DAY]
  -> active opportunity or symbol search
Opportunities [DAY]
  -> candidate row with lifecycle, trigger, invalidation, freshness
Trade Workspace
  -> Decision Summary
  -> Market Driver presentation (when supplied)
  -> WATCH -> ARMED -> TRIGGERED -> TRADEABLE
  -> OPTIONS_SUITABLE (when options data and gates permit)
  -> PORTFOLIO_APPROVED (when account context and gates permit)
  -> Future Execution Readiness (informational only)
```

### Decision checkpoints

1. **Today:** determine whether the session has material market or portfolio changes.
2. **Opportunity:** confirm the candidate is fresh, supported, and in a meaningful
   canonical state; terminal states remain inspectable but are not promoted.
3. **Trade:** see the current state and the next unmet gate before detailed analytics.
4. **Trigger / invalidation:** distinguish planned levels from confirmed trigger events;
   show timestamp and freshness.
5. **Options expression:** show only canonical suitability/candidates. If unavailable,
   retain the valid underlying lifecycle result.
6. **Portfolio risk:** show approval, veto, cap, or unavailable account context.
7. **Future readiness:** show conceptual readiness requirements only after portfolio
   approval; no action control is enabled.

### Alternate outcomes

- `NO_SETUP`: return to opportunity monitoring; WHY remains available.
- `BLOCKED`: show the missing/invalid dependency and a safe navigation path to System.
- `NOT_TRADEABLE`: preserve trigger evidence and show failed tradeability reasons.
- `OPTIONS_NOT_SUITABLE`: preserve the underlying tradeability result.
- `PORTFOLIO_VETOED`: preserve the setup and explain the binding portfolio constraint.
- `EXPIRED`: retain the historical evaluation identity and stop progression.

## Swing Trader

```text
Opportunities [SWING]
  -> candidate / thesis summary
Trade Workspace
  -> multi-timeframe context
  -> structure / regime / direction
  -> canonical lifecycle
  -> trigger / invalidation / targets
  -> options or position structure
  -> portfolio risk
Portfolio monitor or watch state
```

### Decision checkpoints

1. **Opportunity:** rank by canonical state, thesis/playbook, direction, coverage,
   freshness, and risk status rather than by a browser-generated score alone.
2. **Multi-timeframe thesis:** show the selected evaluation timeframe and linked
   higher-timeframe research as separate evidence, never silently blended.
3. **Lifecycle:** preserve the same state language as the day flow. Longer timeframes
   do not create a second lifecycle.
4. **Position structure:** canonical options expression belongs in Trade; exploratory
   payoff modeling belongs in Research.
5. **Portfolio risk:** show concentration, exposure, freshness, and the binding
   constraint when account context exists.
6. **Monitor:** route an approved or developing idea to a future durable watch/idea
   record; until persistence exists, return to filtered Opportunities without claiming
   the idea was saved.

## Long-Term Investor

```text
Portfolio [INVEST] or Research [INVEST]
  -> account position or researched symbol/ETF
Research thesis
  -> sector / relative strength / historical structure
Portfolio position risk
  -> concentration / exposure / supported Greeks
Decision posture
  -> Accumulate / Hold / Review / Reduce (only when supplied by an approved model)
```

### Decision checkpoints

1. **Start from truth:** Portfolio means broker positions; Research holdings mean ETF
   constituents. The UI must label and separate them.
2. **Thesis:** Research owns historical and qualitative context. Every modeled or static
   statement carries provenance.
3. **Position risk:** Portfolio owns account-level exposure, concentration, open risk,
   and freshness. Unknown sector provenance produces partial evidence, not a complete
   concentration pass.
4. **Decision posture:** `Accumulate`, `Hold`, `Review`, and `Reduce` are presentation
   labels only when an approved backend contract supplies them. The frontend must not
   infer them from colors, P/L, or relative strength.
5. **Continuation:** open Trade Workspace only when the user needs a current canonical
   setup evaluation; long-term research itself does not imply a trade setup.

## Cross-Destination Context Contract

Every navigation handoff should preserve, where applicable:

- `symbol`
- `horizon`
- `timeframe`
- `evaluation_timestamp` for replay/review
- `account_id` as a hashed/internal identifier only
- `source_destination` and `source_record_id` for return navigation

The receiving page must re-fetch or receive canonical data by identifier. It must not
reconstruct lifecycle state from URL labels or stale display values.

## Broken-Journey Closure Criteria

| Current break | Design closure criterion |
|---|---|
| Today stops before lifecycle/WHY | Every actionable Today item opens Trade Workspace with the same symbol and horizon. |
| Scanner stops before higher-timeframe/portfolio continuation | Every opportunity opens Trade Workspace; unavailable downstream stages remain explicit. |
| Holdings is not brokerage portfolio | Primary Portfolio uses canonical account snapshots; ETF constituents move to Research with explicit labeling. |

These criteria describe future implementation acceptance. They do not assert that the
current UI already satisfies them.
