# QX Current Frontend Component Inventory

| Component | File | Used by | Classification | Purpose / data source | Reuse and overlap |
|---|---|---|---|---|---|
| `App` / `MarketsDashboard` | `web/src/main.jsx` | All routes / Markets | Mixed | Query router and composite Markets page | Central; Markets duplicates most routed workspaces |
| `QXBentoDashboardLayout` | `web/src/QXBentoDashboardLayout.jsx` | Every routed page | Mixed | Header, theme selector, sidebar; terminal watchlist GET | Highly reusable shell; some header metrics begin as static values |
| `WorkspaceNavigation` | `web/src/WorkspaceNavigation.jsx` | Every routed page | Navigation | Top workspaces, subroutes, quick jumps | Overlaps left sidebar and Markets section links |
| `QXLifecyclePanel` | `web/src/QXLifecyclePanel.jsx` | QX Suite, preview, live baseline | **Canonical V2** | Lifecycle, WHY evidence, provenance, latency, downstream decisions | Reusable canonical presentation; not linked from primary workflows |
| `QXTradingSuite` | `web/src/QXTradingSuite.jsx` | Markets composite | Hybrid | Feature-flagged canonical lifecycle plus local GEX/VWAP/ORB/investor displays | Overlaps terminal, SPX, research, and lifecycle concepts |
| `QXDayTraderTerminal` | `web/src/QXDayTraderTerminal.jsx` | Today and Markets | Legacy/noncanonical | Terminal watchlist/detail, local risk calculator, signal/tape/level displays | Monolithic; duplicates canonical state/trigger concepts |
| `ReferenceRanking` | `web/src/ReferenceRanking.jsx` | Markets | Legacy analytics | Cached rotation ranking supplied by parent | Reusable ranking/table/heatmap modes |
| `MoversWorkspace` | `web/src/MoversWorkspace.jsx` | Markets | Legacy analytics | Cached movers and optional refresh | Overlaps Scanner opportunities |
| `MarketMovers` | `web/src/MarketMovers.jsx` | Movers workspace | Legacy analytics | Generic mover table | Reusable table presentation |
| `QXInstitutionalScanner` | `web/src/QXInstitutionalScanner.jsx` | Scanner and Markets | Legacy/simulated hybrid | Converts movers into client-side scores, entries, stops, option fits | Overlaps movers, terminal, and options; contains fallback candidates |
| `QXOptionsScanner` | `web/src/QXOptionsScanner.jsx` | Scanner and Markets | Legacy/simulated | Legacy scanner POST and strategy presentation | Overlaps canonical options expression and Options Ideas |
| `QXOptionsIdeas` | `web/src/QXOptionsIdeas.jsx` | Scanner, Research, Markets | Modeled research | Modeled contracts/Greeks using underlying quote context | Repeated in three route families |
| `SPXFuturesWorkspace` | `web/src/SPXFuturesWorkspace.jsx` | SPX route and Markets | Mixed live/static/simulated | SPX dashboard, calendar research, futures/macro panels | Duplicates Today and options context |
| `Holdings` | `web/src/Holdings.jsx` | Markets detail | Legacy ETF research | Saved/refreshed fund constituent holdings | Not broker portfolio holdings; no dedicated route |
| `QXResearchStudio` | `web/src/QXResearchStudio.jsx` | Research and Markets | Noncanonical/modeled | Market snapshot and static strengths/risks/action text | Repeated across six Research labels and Markets |
| `QXPositionAdvisor` | `web/src/QXPositionAdvisor.jsx` | Journal and Markets | Legacy standalone | User-entered position evaluation and roll plan | Both Journal routes reuse it despite no journal behavior |
| `QXStrategyWorkspaces` | `web/src/QXStrategyWorkspaces.jsx` | Research and Markets | Standalone calculator | Strategy presets and payoff API | Reusable calculator; overlaps options pages |
| `QXDailyNewsPrompt` | `web/src/QXDailyNewsPrompt.jsx` | Today and Markets | Mostly static/simulated | News-stream and SPX GETs; prompt templates | Duplicated in Today and Markets |
| `QXSystemControl` | `web/src/QXSystemControl.jsx` | Five System routes | Mixed operational/prototype | Real Schwab APIs; browser-local cache/jobs; two-check preflight | Monolithic; no Strategy Rules panel |
| `AIReview` | `web/src/AIReview.jsx` | Markets selected ETF | Legacy AI | Legacy AI status/evidence and gated review POST | Overlaps canonical WHY; not invoked by review journeys |
| `RSLine` | `web/src/RSLine.jsx` | Markets selected ETF | Legacy analytics | Cached relative-strength series | Focused reusable chart |
| `LiveRefresh` | `web/src/LiveRefresh.jsx` | Markets/movers | Provider/cache operation | Polls and can trigger refresh POST | Review harness suppresses mutation by using saved `as_of` data |
| `ErrorBoundary` | `web/src/ErrorBoundary.jsx` | Major panels | Infrastructure | Isolates render failures | Broadly reusable |

## Canonical Placement

Canonical V2 uses `/api/v2/qx/evaluate/{symbol}` through the QX V2 client and is
rendered by `QXLifecyclePanel`. In normal navigation it is nested within QX Suite near
the bottom of the Markets composite page and requires the QX V2 feature flag. The
dedicated fixture preview is clearly labeled `TEST / PREVIEW DATA — NOT LIVE`.

