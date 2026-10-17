# QX Target Page Ownership

## Product Architecture

QX should present one connected decision workflow across three horizons rather than
three separate applications. The primary destinations are:

1. **Today** - what requires attention now.
2. **Opportunities** - what is worth evaluating.
3. **Trade** - what QX sees, what must happen next, and whether risk permits a trade.
4. **Portfolio** - what the brokerage accounts own and what portfolio risk requires.
5. **Research** - deeper analysis, historical context, and strategy investigation.
6. **System** - provider, data, job, and operational health.

`Journal` remains secondary until QX has durable idea, trade, and outcome records.
The horizon (`DAY`, `SWING`, or `INVEST`) is shared context inside these destinations,
not a separate navigation tree.

## Ownership by Destination

### Today

- **Primary user job:** establish the market context and identify material items that
  need attention during the current session.
- **Questions answered:** What matters now? What changed? Which opportunities and
  positions require action or review?
- **Canonical data shown:** market/session context, future market-driver summaries,
  active canonical lifecycle states, material portfolio alerts, freshness and provider
  health only when degraded.
- **Allowed actions:** select horizon, open an opportunity, open Trade Workspace, open
  a portfolio position, acknowledge informational alerts, refresh read-only data.
- **Reusable components:** shell/header, compact lifecycle state badge, market pulse,
  movers/ranking summaries, SPX context, data-quality banner.
- **Current inputs:** `QXDayTraderTerminal`, `QXDailyNewsPrompt`,
  `SPXFuturesWorkspace`, `MoversWorkspace`, and selected header telemetry.
- **Ownership boundary:** Today summarizes and routes. It does not own full scanner
  controls, detailed evidence, deep research, credential operations, or order entry.

### Opportunities

- **Primary user job:** discover and triage candidates for a selected horizon.
- **Questions answered:** Which symbols deserve evaluation? What state are they in?
  What is the trigger, invalidation, tradeability, risk status, and freshness?
- **Canonical data shown:** symbol, horizon, lifecycle state, direction, playbook or
  thesis, future market-driver summary, trigger, invalidation, tradeability, portfolio
  risk status, evidence coverage, and timestamps.
- **Allowed actions:** filter, sort, inspect provenance, save to a watchlist when a
  durable store exists, and open Trade Workspace. No order action.
- **Reusable components:** scanner table/card presentation, ranking tables, lifecycle
  badge, freshness indicator, empty-state and partial-data patterns.
- **Current inputs:** `QXInstitutionalScanner`, `MoversWorkspace`, `MarketMovers`,
  `ReferenceRanking`, and portions of `QXOptionsScanner` and `QXOptionsIdeas`.
- **Ownership boundary:** Opportunities discovers and prioritizes. It does not make the
  final trade decision and must not calculate a second lifecycle in the browser.

### Trade Workspace

- **Primary user job:** evaluate one symbol and one canonical setup from context through
  risk approval.
- **Questions answered:** What is happening? What does QX see? What are we waiting for?
  Where is QX wrong? Is there a trade?
- **Canonical data shown:** the `core_v1` lifecycle, structure, regime, direction,
  playbook, trigger, invalidation, targets, participation, tradeability, options
  expression, portfolio risk, reason codes, evidence, provenance, and stage latency.
- **Allowed actions:** choose symbol/timeframe/horizon, request canonical evaluation,
  expand WHY/audit, inspect downstream availability, and navigate to research or the
  relevant portfolio position. No order action in this milestone.
- **Reusable components:** `QXLifecyclePanel`, V2 client/adapter, selected chart/level
  presentations from the terminal and research surfaces, options and risk summaries.
- **Current inputs:** `QXLifecyclePanel`, `QXTradingSuite`, `QXDayTraderTerminal`,
  `QXResearchStudio`, and the useful presentation portions of options components.
- **Ownership boundary:** Trade is the sole owner of the full canonical decision chain.
  Legacy terminal/scanner state labels must not compete with canonical lifecycle state.

### Portfolio

- **Primary user job:** understand actual brokerage holdings, exposure, constraints,
  and positions requiring attention.
- **Questions answered:** What do I own? What is at risk? Which position or portfolio
  constraint needs review?
- **Canonical data shown:** internal/hashed account identity, balances needed for risk,
  positions, P/L, exposure, concentration with provenance, Greeks where available,
  open-trade risk, constraints, freshness, and portfolio-risk decisions.
- **Allowed actions:** select account, inspect position risk, open Trade Workspace or
  Research, and refresh read-only account data. No broker writes.
- **Reusable components:** account snapshot status, portfolio-risk summary, exposure and
  concentration visualizations, position table, `QXPositionAdvisor` presentation ideas.
- **Current inputs:** canonical account snapshot and portfolio-risk result. The current
  `Holdings` component is not an input to broker portfolio ownership.
- **Ownership boundary:** broker positions and ETF constituent research remain separate.

### Research

- **Primary user job:** investigate a symbol, sector, ETF, strategy, or historical
  hypothesis without crowding the live decision screen.
- **Questions answered:** What is the broader thesis? How has structure behaved? What
  does relative strength show? How would a strategy behave historically?
- **Canonical data shown:** symbol and ETF research, sector rotation, relative strength,
  historical structure, strategy studies, backtests, and supported qualitative context.
- **Allowed actions:** select subject and period, compare, run read-only research,
  inspect provenance, and send a symbol/thesis context to Trade Workspace.
- **Reusable components:** `QXResearchStudio`, `ReferenceRanking`, `RSLine`, renamed ETF
  constituent research from `Holdings`, and `QXStrategyWorkspaces`.
- **Current inputs:** the six current Research labels and research portions of the
  oversized Markets page.
- **Ownership boundary:** Research may explain or compare; it does not publish a
  canonical live lifecycle state or approve portfolio risk.

### System

- **Primary user job:** verify QX operational readiness and manage local integrations.
- **Questions answered:** Are providers authenticated and healthy? Are data and jobs
  current? What failed and when?
- **Canonical data shown:** Schwab status, data source health, cache/job/run status,
  pipeline version, and audit-safe diagnostics.
- **Allowed actions:** local credential management, health checks, safe refresh/retry,
  and inspection of configuration metadata. No trading actions.
- **Reusable components:** `QXSystemControl`, status cards, health tables, provenance
  labels, and run-history presentation when backed by persistent data.
- **Current inputs:** all five System routes.
- **Ownership boundary:** prototype browser-local values must be labeled as such until
  backed by real persistence.

### Journal (Secondary)

- **Primary user job:** review durable ideas, decisions, trades, and outcomes.
- **Current status:** no persisted journal workflow exists. Keep the destination
  secondary and unavailable rather than relabeling `QXPositionAdvisor` as a journal.
- **Activation requirement:** a reviewed persistence contract linking an idea to a
  canonical evaluation, optional future execution record, and outcome.

## Existing Surface Classification

| Current route/surface | Target owner | Classification | Design disposition |
|---|---|---|---|
| `relative_strength` | Research / Today / Opportunities | MERGE | Break the composite page into owned summaries; retain route as a temporary alias. |
| `command_center` | Today | MERGE | Contribute intraday context; remove competing state language during migration. |
| `morning_report` | Today | MERGE | Become a Today view/section for changes, not a duplicate page. |
| `daily_workflow` | Today | MERGE | Become a Today preparation view/section, not a duplicate page. |
| `spx_nq_futures` | Today / Research / Trade | MOVE | Compact pulse on Today; deeper context in Research; relevant context in Trade. |
| `sector_rotation` | Research / Today | MOVE | Full analysis in Research; material summary on Today. |
| `scan` | Opportunities | MERGE | Primary legacy input to the unified discovery surface. |
| `broad_watchlist` | Opportunities | MERGE | Become a filter/saved-view concept after persistence exists. |
| `heatmap` | Opportunities / Research | MOVE | Visualization mode, not a duplicate route bundle. |
| `ticker_history` | Research | MERGE | Become the default instrument research view. |
| `options_ideas` | Research / Trade | MOVE | Research owns modeling; Trade owns canonical options expression. |
| `options_flow` | Research | DEPRECATE_LATER | Keep route until a distinct supported flow view exists. |
| `liquidity_map` | Research | DEPRECATE_LATER | Keep route until a distinct supported liquidity view exists. |
| `backtest` | Research | MOVE | Dedicated Research mode when actual controls/results exist. |
| `strategy_lab` | Research | KEEP | Retain the payoff/strategy tool under Research after API cleanup. |
| `idea_tracking` | Portfolio / Research | MOVE | Move position analysis; do not present it as durable idea tracking. |
| `journal` | Journal | DEPRECATE_LATER | Keep route as an explicit unavailable/coming-later surface. |
| `data_cache` | System | SYSTEM_ONLY | Retain but distinguish real metrics from placeholders. |
| `schwab` | System | KEEP | Retain real local credential and provider-health workflow. |
| `jobs` | System | SYSTEM_ONLY | Retain; label simulations until backed by actual jobs. |
| `run_history` | System | SYSTEM_ONLY | Rename or implement persistent run history later; current content is preflight. |
| `strategy_rules` | System | SYSTEM_ONLY | Keep route hidden/secondary until a real read-only rules view exists. |

No route is deleted by this design. Existing aliases remain compatibility paths until
their consumers and tests move to the target destinations.
