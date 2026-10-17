# BE2 UI Projection: Displaying Multi-Timeframe Context Without UI Redesign

## 1. Existing Workspace Review

The QX frontend currently exposes the trading horizon in four key workspaces:

1. **Today (`web/src/QXTodayWorkspace.jsx`)**:
   - Displays a horizontal toggle: `[ DAY | SWING | INVEST ]`.
   - Opportunity cards display symbol, horizon, and primary timeframe (e.g. `SPY · DAY · 5m`).
2. **Opportunities (`web/src/QXOpportunitiesWorkspace.jsx`)**:
   - Filter bar contains Horizon selector and State filter.
   - Grid cards list each candidate with primary timeframe badge and directional pill (`BULLISH`, `BEARISH`).
3. **Trade (`web/src/QXTradeWorkspace.jsx`)**:
   - Shows active trade setup with Trade Metrics bar: `Horizon`, `Playbook`, `Direction`, `Target`, `Invalidation`.
   - Evidence summary details available factors.
4. **Research (`web/src/QXResearchWorkspace.jsx`)**:
   - Provides macro and longer-horizon context panels for deep ticker exploration.

---

## 2. Multi-Timeframe UX Additions (Non-Disruptive & Additive)

No UI redesign or layout overhaul is permitted or required. The existing Bento grid and typography tokens can absorb multi-timeframe context through minimal, highly informative micro-elements:

### A. Opportunities Workspace Cards
- **Current display**: `SPY · DAY · 5m`
- **Additive Projection**:
  - Add a subtle secondary timeframe alignment badge:
    ```
    [ 5m Setup ] [ HTF 1h: BULLISH ]
    ```
  - If HTF is aligned: subtle green border/pill (`HTF ALIGNED`).
  - If HTF is conflicting: subtle amber pill (`HTF CONFLICT`).
  - If HTF is unavailable: neutral gray pill (`HTF N/A`).

### B. Trade Workspace Evidence Breakdown
- In the Direction Factors table:
  - Factor #7 is currently labeled `Higher Timeframe Structure`.
  - When populated, it displays:
    - **Factor Name**: `HTF Structure (1h)`
    - **State**: `BULLISH BOS (Confirmed)`
    - **Score**: `+100.0`
    - **Effective Weight**: `10.0%`
    - **Freshness**: `FRESH (3 bars ago)`
  - If HTF is missing or stale:
    - Displays `UNAVAILABLE (No completed HTF bars before T_eval)`.

### C. Today Workspace Top Attention List
- Opportunity cards display multi-timeframe concordance as a micro-tag:
  - `SPY 5m · HTF Concurrence 100%`

---

## 3. Data Model Compatibility for Web Clients

The frontend client already models opportunities via `canonicalOpportunityFromRecord` in `web/src/qx-opportunities-model.js`.
- It consumes `data_dependencies`, `evidence_coverage`, and `coverage_status`.
- Introducing multi-timeframe details into `evidence_summary` and `data_dependencies` requires zero breaking changes to JavaScript parsing.
