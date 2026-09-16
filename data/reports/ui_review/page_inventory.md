# QX Current Page and Route Inventory

Generated from the current React application. Routes use `/?page=<route>` and share
the context parameters `symbol`, `etf`, `universe`, `sector`, `period`, `as_of`, and
`snapshot`. No route is itself feature-flagged; only the canonical lifecycle embedded
inside QX Suite is feature-flagged and defaults off.

## Routed Pages

| # | Page | Route / Navigation | Purpose and major components | Data and actions | Classification / duplication / known gaps |
|---:|---|---|---|---|---|
| 1 | Relative Strength | `/` or `?page=relative_strength`; Markets top nav | Composite market workspace: ranking, movers, advisor, research, strategies, RS chart, AI Review, holdings, terminal, SPX, prompts, options, scanner, QX Suite | Cached rotation/movers/RS/holdings; terminal/SPX GETs; filters, symbol selection and refresh controls | Mixed legacy/live/prototype; duplicates most specialized workspaces; canonical lifecycle appears only in QX Suite when enabled |
| 2 | Command Center | `?page=command_center`; Today / Terminal | Day Trader Terminal plus Daily News & Prompt Deck | `/api/terminal/*`, `/api/news-stream`, `/api/spx-dashboard`; ticker selection, local risk inputs, prompt controls | Legacy/mixed; identical render bundle to Morning Report and Daily Workflow; no canonical lifecycle |
| 3 | Morning Report | `?page=morning_report`; Today → Changes | Same Day Trader Terminal and prompt/news surface | Same as Command Center | Label-only duplicate; no distinct report-comparison workflow in React |
| 4 | Daily Workflow | `?page=daily_workflow`; Today → Preparation | Same Day Trader Terminal and prompt/news surface | Same as Command Center | Label-only duplicate; no distinct preparation workflow in React |
| 5 | SPX / NQ Futures | `?page=spx_nq_futures`; Markets / Futures | SPX plan, dealer levels, calendars, macro/futures context | `/api/spx-dashboard`, `/api/spx-calendars`; tabs and local paper-calendar action | Mixed live/static/simulated; no canonical lifecycle |
| 6 | Sector Rotation | `?page=sector_rotation`; Markets → Sector Archive | Same composite surface as Relative Strength | Same data and actions as Relative Strength | Label-only duplicate; no distinct archive implementation |
| 7 | Scanner | `?page=scan`; Scanner top/side nav | Institutional Scanner, Options Scanner V1, Options Ideas | Movers GET plus optional scan POSTs; filters, candidate selection, scan forms | Legacy/simulated; overlaps Markets, options, and terminal surfaces |
| 8 | Broad Watchlist | `?page=broad_watchlist`; Scanner subnav | Same three-component Scanner bundle | Same as Scanner | Label-only duplicate; no distinct watchlist implementation |
| 9 | Heatmap | `?page=heatmap`; Scanner subnav | Same three-component Scanner bundle | Same as Scanner | Label-only duplicate; no dedicated heatmap view |
| 10 | Ticker History | `?page=ticker_history`; Research top nav | Research Studio, Options Ideas, Strategy Workspaces | Market snapshot GET; symbol input; modeled options and payoff controls | Noncanonical/modeled; no ticker-history timeline |
| 11 | Options Ideas | `?page=options_ideas`; Research / Ideas Hub | Same Research bundle | Same as Ticker History | Duplicate route and quick-jump destination; options are modeled research output |
| 12 | Options Flow | `?page=options_flow`; Research subnav | Same Research bundle | Same as Ticker History | No distinct flow UI or visible flow-analysis call |
| 13 | Liquidity Map | `?page=liquidity_map`; Research subnav | Same Research bundle | Same as Ticker History | No liquidity-map visualization |
| 14 | Backtest | `?page=backtest`; Research subnav | Same Research bundle | Same as Ticker History | No backtest controls or results |
| 15 | Strategy Lab | `?page=strategy_lab`; Research subnav | Same Research bundle; strategy payoff editor is the most relevant panel | Strategy workspace/payoff API; leg editing | Duplicate Research bundle; hard-coded loopback API calls in strategy component |
| 16 | Idea Tracking | `?page=idea_tracking`; Journal / Advisor | Position Advisor form and result panel | `/api/position-advisor`; user-entered position analysis | Legacy standalone analysis; no saved idea tracking |
| 17 | Outcome Journal | `?page=journal`; Journal subnav | Same Position Advisor | Same as Idea Tracking | No journal entries, outcomes, persistence, or history |
| 18 | Data Cache | `?page=data_cache`; System top nav | System Control cache panel | Browser-local placeholder cache metrics and timer refresh | Prototype; values are not a persisted cache inventory |
| 19 | Schwab API | `?page=schwab`; System subnav | Credential status and manual OAuth controls | `/api/system/schwab/*`; save/test/clear/auth actions | Real local operational integration; secrets are masked; captures redact client-ID fragments |
| 20 | Jobs | `?page=jobs`; System subnav | Scheduled-job cards and local log panel | Browser-local job simulation | Prototype; no jobs API execution/history |
| 21 | Run History | `?page=run_history`; System subnav | FastAPI/Schwab preflight summary | `/api/ai/status`, Schwab status GET | Not a run-history browser; two-check operational status only |
| 22 | Strategy Rules | `?page=strategy_rules`; System subnav | System shell | None | Route exists, but System Control has no matching tab/content panel |

## Side Navigation Workspaces

| Label | Destination | Current meaning |
|---|---|---|
| Terminal | `?page=command_center` | Today’s legacy Day Trader Terminal bundle |
| Ideas Hub | `?page=options_ideas` | Research bundle, not a dedicated ideas-only page |
| Futures | `?page=spx_nq_futures` | SPX/Futures workspace |
| Scanner | `?page=scan` | Three-component Scanner bundle |
| Advisor | `?page=idea_tracking` | Position Advisor, not an idea journal |
| System | `?page=data_cache` | System Control cache panel |

## Quick-Jump Workspaces

Quick jumps are anchors inside the long Relative Strength page. From other routes the
UI first navigates to Markets, then scrolls to the anchor.

| Label | Anchor | Surface / status |
|---|---|---|
| Options Ideas Hub | `#options-ideas-hub` | Modeled options ideas |
| Research Studio | `#research-studio` | Symbol structure/research snapshot |
| Options Scanner V1 | `#options-scanner-v1` | Legacy options scanner |
| SPX Command | `#spx-dashboard` | SPX/Futures workspace embedded again |
| Prompt Studio | `#daily-prompt` | Daily prompt/news deck |
| Day Trader Terminal | `#qx-terminal` | Legacy terminal embedded again |
| QX Suite | `#qx-suite` | Mixed suite; canonical lifecycle is feature-flagged here |
| Sector Ranking | `#ranking` | Cached relative-strength ranking |
| Market Movers | `#movers` | Cached mover tables |
| AI Review | `#ai-review` | Legacy AI evidence; available only with selected ETF detail |
| Holdings | `#holdings` | ETF constituent holdings, not brokerage-account positions |

The displayed `F0`–`F9` labels do not have keyboard handlers. Options Scanner and SPX
Command both display `F2`.

## Route Aliases

| Alias | Canonical destination | Secondary intent |
|---|---|---|
| `qx`, `scanner` | Scanner | None |
| `watchlist` | Broad Watchlist | None |
| `spx_dashboard` | SPX / NQ Futures | None |
| `liquidity` | Liquidity Map | None |
| `performance` | Idea Tracking | None |
| `pipeline`, `pipeline_control` | Jobs | `job_view=Pipeline` |
| `automation_control` | Jobs | `job_view=Schedule` |
| `history` | Run History | `history_view=Scans` |
| `workflow_history` | Run History | `history_view=Workflows` |
| `command_snapshots` | Run History | `history_view=Snapshots` |

System Control does not currently consume the requested `job_view` or `history_view`
distinctions, so those aliases resolve to the same visible Jobs or Run History panel.
