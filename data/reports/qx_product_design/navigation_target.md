# Target Navigation and Route Mapping

## Primary Navigation

```text
Today | Opportunities | Trade | Portfolio | Research | System
```

Optional secondary destination:

```text
Journal
```

The left sidebar and top navigation should not remain two competing global navigation
systems. Retain one responsive primary navigation. Contextual controls and commands
belong inside the owning destination.

## Proposed Destination Routes

These names are design targets, not implemented routes:

| Destination | Proposed route | Default purpose |
|---|---|---|
| Today | `?page=today` | Material current-session summary |
| Opportunities | `?page=opportunities` | Horizon-filtered discovery |
| Trade | `?page=trade` | One canonical evaluation |
| Portfolio | `?page=portfolio` | Read-only broker positions and risk |
| Research | `?page=research` | Instrument/ETF/strategy/history analysis |
| System | `?page=system` | Operational health and integrations |
| Journal | `?page=journal` | Secondary; durable records only when implemented |

Context parameters should be explicit and shared: `symbol`, `horizon`, `timeframe`,
`evaluation_timestamp`, and safe internal record identifiers.

## Complete Existing Route Map

| Existing route | Current label | Target destination/mode | Disposition |
|---|---|---|---|
| `relative_strength` | Relative Strength | Research: ETF & Sector; summaries feed Today/Opportunities | Temporary alias, then DEPRECATE_LATER |
| `command_center` | Command Center | Today | MERGE |
| `morning_report` | Morning Report | Today: Changes view | MERGE |
| `daily_workflow` | Daily Workflow | Today: Preparation view | MERGE |
| `spx_nq_futures` | SPX / NQ Futures | Today pulse + Research market context | MOVE |
| `sector_rotation` | Sector Rotation | Research: ETF & Sector | MOVE |
| `scan` | Scanner | Opportunities | MERGE |
| `broad_watchlist` | Broad Watchlist | Opportunities: watchlist filter/view | MERGE |
| `heatmap` | Heatmap | Opportunities visualization or Research comparison | MOVE |
| `ticker_history` | Ticker History | Research: Instrument/Historical | MERGE |
| `options_ideas` | Options Ideas | Research: Options & Strategy | MOVE |
| `options_flow` | Options Flow | Research placeholder until distinct supported data exists | DEPRECATE_LATER |
| `liquidity_map` | Liquidity Map | Research placeholder until distinct visualization exists | DEPRECATE_LATER |
| `backtest` | Backtest | Research: Backtests | MOVE |
| `strategy_lab` | Strategy Lab | Research: Options & Strategy | KEEP within Research |
| `idea_tracking` | Idea Tracking | Portfolio position review / future Journal | MOVE |
| `journal` | Outcome Journal | Journal | KEEP secondary, unavailable until persistent |
| `data_cache` | Data Cache | System: Data | SYSTEM_ONLY |
| `schwab` | Schwab API | System: Providers | KEEP |
| `jobs` | Jobs | System: Jobs | SYSTEM_ONLY |
| `run_history` | Run History | System: Preflight now; Runs when persistent | SYSTEM_ONLY |
| `strategy_rules` | Strategy Rules | System: Rules metadata | SYSTEM_ONLY; hide until content exists |

## Existing Alias Compatibility

| Existing alias | Current target | Future compatibility target |
|---|---|---|
| `qx`, `scanner` | `scan` | `opportunities` |
| `watchlist` | `broad_watchlist` | `opportunities` with watchlist view |
| `spx_dashboard` | `spx_nq_futures` | `today` or `research` market-context mode |
| `liquidity` | `liquidity_map` | `research` liquidity mode when implemented |
| `performance` | `idea_tracking` | `portfolio` position review; do not imply journal history |
| `pipeline`, `pipeline_control` | `jobs` | `system` jobs/pipeline mode |
| `automation_control` | `jobs` | `system` schedule mode |
| `history` | `run_history` | `system` runs mode |
| `workflow_history` | `run_history` | `system` workflows mode |
| `command_snapshots` | `run_history` | `system` snapshots mode |

Aliases should remain during migration and emit no behavioral differences. Remove only
after consumer inventory, analytics, tests, and rollback validation.

## Quick-Jump Conversion

The current quick-jump bar targets anchors inside the oversized Markets page. Replace
it with a command/search affordance after destination routes exist.

| Current quick jump | Target command |
|---|---|
| Options Ideas Hub | Open Research -> Options & Strategy |
| Research Studio | Open Research -> Instrument for current symbol |
| Options Scanner V1 | Open legacy comparison from Opportunities or System/Legacy |
| SPX Command | Open Today market pulse or Research market context |
| Prompt Studio | Open Research/context panel; not a primary destination |
| Day Trader Terminal | Open Today or Trade for current symbol |
| QX Suite | Open Trade for current symbol |
| Sector Ranking | Open Research -> ETF & Sector |
| Market Movers | Open Opportunities with movers source/filter |
| AI Review | Open legacy evidence inside Research; not canonical WHY |
| Holdings | Open Research -> ETF Constituents |

Displayed `F0`-`F9` labels should be removed unless actual accessible keyboard commands
are implemented. Duplicate `F2` labeling must not carry forward.

## Secondary Navigation by Destination

```text
Today:          Overview | Changes | Preparation
Opportunities:  List | Cards | Heatmap | Watchlist (when persistent)
Trade:          Summary | Chart/Context | WHY/Audit
Portfolio:      Overview | Positions | Exposure | Constraints
Research:       Instrument | ETF & Sector | Options & Strategy | Historical | Backtests
System:         Providers | Data | Jobs | Runs | Rules
Journal:        Ideas | Trades | Outcomes (only when persistent)
```

Secondary items should be tabs/modes only when they show distinct content. They should
not be separate labels rendering the same component bundle.

## Navigation Rules

- One global navigation system across desktop and mobile.
- Preserve symbol/horizon/timeframe when moving from Opportunities to Trade or Research.
- Never encode a lifecycle state in the URL as truth; use a canonical evaluation ID.
- Show provenance/legacy status at the content level, not as another navigation tree.
- System routes never appear as trading workflow steps except for resolving a data
  health problem.
- Portfolio is visible even when unavailable so the product does not relabel ETF
  constituent research as account holdings.

## Migration Safety

During migration, existing URLs continue to resolve through aliases. A compatibility
layer routes old links to the correct destination/mode and provides a return path. Route
deletion is explicitly outside this milestone.
