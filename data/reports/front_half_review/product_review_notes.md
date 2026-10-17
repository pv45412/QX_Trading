# QX Front-Half Product Review Notes

## Review Scope

This review covers the current read-only front-half journey:

**Attention → Discovery → Decision**

**Today → Opportunities → Trade Workspace**

Deterministic fixture data is used because a live canonical opportunity-list endpoint is not available. Every fixture surface visibly states `TEST / PREVIEW DATA - NOT LIVE`.

## A. Does Today immediately communicate what matters now?

**Yes.** The page opens with a clear “What Matters Now?” framing, then presents Market Pulse and the highest-priority canonical opportunities within the desktop first viewport. Market Drivers remain visibly unavailable instead of being inferred. Position and data-health exceptions remain secondary unless material.

Observation: the unavailable Market Drivers slot consumes meaningful space, but its presentation is truthful and visually subordinate to Market Pulse and active opportunities.

## B. Does Opportunities make discovery easy without becoming another Trade page?

**Yes.** Horizon, text, lifecycle, direction, and sort controls are prominent. Rows expose enough state, trigger/risk, coverage, freshness, and portfolio context to triage, while detailed lifecycle evidence remains collapsed or belongs to Trade.

Observation: nine fixture rows create a long mobile page. The first row and filters remain easy to reach, but later candidates require substantial scrolling.

## C. Does Trade answer the five decision questions clearly?

**Yes.** Trade explicitly answers:

- What is happening?
- What does QX see?
- What are we waiting for?
- Where is QX wrong?
- Is there a trade?

On desktop these five answers and the key decision facts appear before the detailed lifecycle. On mobile they remain in the same order after the compact context and identity controls. Trigger, invalidation, options suitability, portfolio state, and WHY evidence remain available without introducing execution controls.

## D. Are Today and Opportunities duplicating too much information?

**No material duplication was observed.** Today uses a three-row attention summary; Opportunities adds filters and richer triage fields. State, direction, trigger/risk, and freshness repeat intentionally so identity can be verified during handoff.

## E. Is the source/state distinction clear?

**Yes.** The current UI distinguishes:

- canonical data with `CANONICAL / CORE_V1` labels;
- legacy movement context with `LEGACY SOURCE` badges;
- unavailable fields with explicit `UNAVAILABLE` labels;
- blocked states with lifecycle and publication warnings;
- fixtures with the prominent `TEST / PREVIEW DATA - NOT LIVE` banner.

The distinctions remain visible on mobile, although supporting text is necessarily smaller.

## F. Are there unnecessary clicks between Today, Opportunities, and Trade?

**No blocking extra step was observed.** Today supports a direct one-click route to Trade for an active opportunity. The broader discovery path uses two intentional actions: `View all opportunities`, then `Open Trade` on the selected canonical row.

## G. Is the most important information above the fold?

**Desktop: yes.** Today shows market state and active opportunities; Opportunities shows filters and the first candidates; Trade shows identity, lifecycle decision, five decision questions, and core facts.

**Mobile: mostly.** Today preserves market state first. Opportunities shows controls and the first candidate. Trade shows context and the decision summary first, while detailed options, portfolio risk, and WHY evidence require scrolling.

## H. Does mobile preserve the decision hierarchy?

**Yes.** Mobile retains the same semantic order instead of rearranging lifecycle meaning. The principal cost is vertical length, especially for the full Opportunities list and expanded Trade evidence.

## Context-Handoff Findings

Both observed fixture routes passed:

- Today → Trade
- Opportunities → Trade

The following remained stable in each route:

- symbol: `QQQ`
- horizon: `SWING`
- timeframe: `1h`
- evaluation timestamp: `2026-09-16T14:35:00Z`
- evaluation identity: `fixture-swing-triggered-qqq`
- canonical lifecycle state: `TRIGGERED`

Observation only: after arrival, the global Trade shell adds its default `etf=XLK` query context. It does not change the required canonical identity fields or lifecycle state, but it creates unrelated ETF context in the Trade URL/context strip. No behavior was changed in this review-only milestone.

## Review Conclusion

The current front half reads coherently as:

1. Today identifies what needs attention.
2. Opportunities supports comparative discovery and triage.
3. Trade owns the complete canonical decision lifecycle.

No Portfolio work, redesign, lifecycle change, trading-rule change, execution behavior, or Phase 11 work was performed.
