# QX Current User Experience Findings

This document records current-state behavior only. It does not prescribe a redesign,
route deletion, threshold change, or migration.

## Factual Observations

1. The navigation exposes 22 route labels, but current rendering collapses them into
   seven substantive page bundles.
2. Morning Report and Daily Workflow display the same content as Command Center.
3. Broad Watchlist and Heatmap display the same content as Scanner.
4. Six Research route labels display the same Research Studio, Options Ideas, and
   Strategy Workspaces bundle.
5. Idea Tracking and Outcome Journal both display Position Advisor; no saved journal
   or outcome-history interface is present.
6. Relative Strength functions as a long composite home page containing market,
   research, holdings, scanner, options, terminal, futures, prompt, AI, and QX Suite
   surfaces.
7. Top navigation, left navigation, section navigation, and quick jumps offer multiple
   paths to several identical components.
8. Quick-jump `F0`–`F9` labels are visual only; no matching keyboard handling exists.
9. Options Scanner and SPX Command both display the `F2` quick-jump label.
10. Canonical V2 lifecycle is not presented in Today, Scanner, Research, or Journal.
    It is feature-flagged inside QX Suite on Markets and also available through
    unlinked preview/live-baseline pages.
11. Legacy terminal and scanner surfaces use state, trigger, stop, R:R, and option
    concepts that overlap canonical lifecycle concepts without shared presentation.
12. Holdings displays ETF constituents and concentration, not brokerage-account
    positions or canonical portfolio-risk evidence.
13. The `strategy_rules` route is visible but has no corresponding content panel.
14. System combines real Schwab status/credential operations with browser-local cache
    and job simulations; Run History is a status/preflight panel rather than history.
15. Several pages combine live or cached inputs with modeled, generated, or static
    outputs. Those distinctions are not always equally prominent in every panel.
16. The day-trader journey stops before canonical lifecycle/WHY because no direct link
    is present from Today’s terminal.
17. The swing-trader journey can inspect a legacy scanner blueprint but stops before
    canonical higher-timeframe and portfolio-risk stages.
18. The long-term-investor journey can inspect ETF holdings and open research surfaces,
    but no linked brokerage portfolio, position-risk, and durable thesis workflow exists.

## Possible Product Questions

1. Which of the 22 labels are intended to become distinct workflows versus alternate
   names for a shared workspace?
2. Which surface should own the canonical lifecycle as the primary user destination?
3. Should legacy scanner/terminal evidence remain visible beside canonical evidence,
   and if so, how should their provenance be distinguished?
4. Is “Portfolio” intended to mean ETF constituent research, broker account positions,
   canonical portfolio risk, or separate experiences?
5. What saved objects should Idea Tracking and Outcome Journal own?
6. Which operational System panels are intended to become real persisted views?
7. Should quick jumps remain global if their targets live only on the Markets composite?
8. Which modeled/static datasets require stronger visible provenance labels?

These are review questions only; no product choice has been implemented.

