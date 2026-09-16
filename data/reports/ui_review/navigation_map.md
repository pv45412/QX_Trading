# QX Current Navigation Map

## Hierarchy

```text
QX PLATFORM
├─ Top workspace navigation
│  ├─ Today: Command Center | Morning Report | Daily Workflow
│  ├─ Markets: Relative Strength | SPX / NQ Futures | Sector Rotation
│  ├─ Scanner: Scanner | Broad Watchlist | Heatmap
│  ├─ Research: Ticker History | Options Ideas | Options Flow | Liquidity Map | Backtest | Strategy Lab
│  ├─ Journal: Idea Tracking | Outcome Journal
│  └─ System: Data Cache | Schwab API | Jobs | Run History | Strategy Rules
├─ Left sidebar
│  └─ Terminal | Ideas Hub | Futures | Scanner | Advisor | System
└─ Quick-jump command bar
   └─ Options Ideas | Research | Options Scanner | SPX | Prompt | Terminal | QX Suite | Ranking | Movers | AI Review | Holdings
```

All primary React navigation is query-parameter based. Top navigation changes to the
first route in a workspace. Workspace subnavigation changes the `page` value while
preserving validated context parameters. Quick jumps use hash anchors on the Markets
composite page.

## Major Workflow Paths

```text
Today → Day Trader Terminal → legacy signal detail
                                  └─ no direct canonical lifecycle/WHY link

Scanner → candidate row → legacy setup blueprint / modeled option fit
                              └─ no canonical portfolio-risk continuation

Markets → selected ETF → RS chart → AI Review → ETF holdings
       └─ Research / Terminal / SPX / Options / Scanner / QX Suite are repeated below

System → Schwab API → local credential status and manual OAuth controls
```

## Duplicate Entry Points

- Terminal: Today top navigation, left sidebar, Markets section navigation, and quick jump.
- Scanner: Scanner workspace, Markets embedded scanner, and quick jump.
- Research: six Research route names, Markets embedded Research Studio, and quick jump.
- Options: Ideas Hub sidebar, Research Options Ideas, Markets Options Ideas, Options Scanner, and two quick jumps.
- SPX: Futures sidebar/route, Markets embedded SPX workspace, and SPX quick jump.
- Advisor: Journal routes, Markets embedded Position Advisor, and left sidebar.
- System: top navigation and left sidebar; five route labels share one component.

## Orphaned or Unlinked Surfaces

- `qx-v2-preview.html` and `qx-v2-live-baseline.html` are direct auxiliary entrypoints,
  not normal application navigation destinations.
- `strategy_rules` is linked but has no corresponding System Control content panel.
- Canonical lifecycle is located inside QX Suite at the bottom of Markets when its
  feature flag is enabled; Today, Scanner, Research, and Journal do not link to it.

## Pages Mixing Jobs

- Relative Strength combines market overview, research, portfolio-like holdings,
  scanners, options, terminal, futures, AI, and canonical lifecycle surfaces.
- Scanner combines equity candidates, legacy option scanning, and modeled ideas.
- Research combines underlying research, modeled ideas, and payoff construction for
  every Research route name.
- System combines real credential management with browser-local cache/job prototypes.

No deletion or restructuring recommendation is made in this review.

