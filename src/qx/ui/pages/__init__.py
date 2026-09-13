from qx.ui.app_shell import AppPage, lazy_page_renderer


PAGES = [
    AppPage(
        title="Scanner",
        caption="Find rectangle breakout candidates across custom symbols or index universes.",
        render=lazy_page_renderer("qx.ui.pages.scan", "render_scan_page"),
    ),
    AppPage(
        title="Daily Workflow",
        caption="Combine market regime, sector leadership, and saved scan results.",
        render=lazy_page_renderer("qx.ui.pages.today_views", "render_preparation_page"),
    ),
    AppPage(
        title="Command Center",
        caption="Morning decision page for regime, SPX, sectors, watchlist, and options.",
        render=lazy_page_renderer("qx.ui.pages.command_center", "render_command_center_page"),
    ),
    AppPage(
        title="Broad Watchlist",
        caption="Rank symbols with independent momentum, trend, sector, liquidity, volume, and scanner signals.",
        render=lazy_page_renderer("qx.ui.pages.watchlist", "render_watchlist_page"),
    ),
    AppPage(
        title="Jobs",
        caption="Run data cache, scanner, workflow, and history persistence in one pass.",
        render=lazy_page_renderer("qx.ui.pages.jobs", "render_jobs_page"),
    ),
    AppPage(
        title="Sector Rotation",
        caption="Track sector ETF leadership and scanner candidates by sector.",
        render=lazy_page_renderer("qx.ui.pages.sector_rotation", "render_sector_rotation_page"),
    ),
    AppPage(
        title="Run History",
        caption="Compare saved daily workflow snapshots over time.",
        render=lazy_page_renderer("qx.ui.pages.run_history", "render_run_history_page"),
    ),
    AppPage(
        title="SPX / NQ Futures",
        caption="Build daily futures context for ES, NQ, rates, dollar, crude, and gold.",
        render=lazy_page_renderer("qx.ui.pages.spx_dashboard", "render_spx_dashboard_page"),
    ),
    AppPage(
        title="Liquidity Map",
        caption="Build day-trading levels from price structure and option-chain walls.",
        render=lazy_page_renderer("qx.ui.pages.liquidity_map", "render_liquidity_map_page"),
    ),
    AppPage(
        title="Options Ideas",
        caption="Generate first-pass options ideas from qx watchlists.",
        render=lazy_page_renderer("qx.ui.pages.options_ideas", "render_options_ideas_page"),
    ),
    AppPage(
        title="Ticker History",
        caption="Review complete OHLCV history, price structure, returns, and drawdown for one ticker.",
        render=lazy_page_renderer("qx.ui.pages.ticker_history", "render_ticker_history_page"),
    ),
    AppPage(
        title="Options Flow",
        caption="Score directional call/put flow with price, IV, liquidity, and regime filters.",
        render=lazy_page_renderer("qx.ui.pages.options_flow", "render_options_flow_page"),
    ),
    AppPage(
        title="Idea Tracking",
        caption="Review saved options ideas and their recorded outcomes.",
        render=lazy_page_renderer("qx.ui.pages.performance", "render_performance_page"),
    ),
    AppPage(
        title="Schwab API",
        caption="Check Schwab auth configuration and token refresh readiness.",
        render=lazy_page_renderer("qx.ui.pages.schwab", "render_schwab_page"),
    ),
    AppPage(
        title="Strategy Rules",
        caption="Review the active rule profiles and the rectangle scoring model.",
        render=lazy_page_renderer("qx.ui.pages.strategy", "render_strategy_page"),
    ),
    AppPage(
        title="Strategy Lab",
        caption="Compare scanner settings using historical breakout behavior.",
        render=lazy_page_renderer("qx.ui.pages.strategy_lab", "render_strategy_lab_page"),
    ),
    AppPage(
        title="Data Cache",
        caption="Review local market data coverage before running large scans.",
        render=lazy_page_renderer("qx.ui.pages.data_cache", "render_data_cache_page"),
    ),
    AppPage(
        title="Outcome Journal",
        caption="Record explicit paper or live trade outcomes separately from research ideas.",
        render=lazy_page_renderer("qx.ui.pages.journal", "render_journal_page"),
    ),
    AppPage(
        title="Morning Report",
        caption="Turn the latest saved scan into watchlist buckets for review.",
        render=lazy_page_renderer("qx.ui.pages.today_views", "render_changes_page"),
    ),
    AppPage(
        title="Heatmap",
        caption="Visualize the latest saved scan by score, quality, and setup status.",
        render=lazy_page_renderer("qx.ui.pages.heatmap", "render_heatmap_page"),
    ),
    AppPage(
        title="Backtest",
        caption="Measure historical scanner signal behavior before trusting a setup.",
        render=lazy_page_renderer("qx.ui.pages.backtest", "render_backtest_page"),
    ),
]
