export const primaryWorkspaceRoutes = [
 ['today', 'Today', 'Today', 'command_center'],
 ['opportunities', 'Opportunities', 'Opportunities', 'scan'],
 ['trade', 'Trade', 'Trade Workspace', 'trade'],
 ['portfolio', 'Portfolio', 'Portfolio', 'portfolio'],
 ['research', 'Research', 'Research', 'ticker_history'],
 ['system', 'System', 'System', 'system_overview'],
].map(([page, workspace, title, surface]) => ({
 page, workspace, title, label: workspace, surface, target: true, targetPage: page,
}));

export const legacyWorkspaceRoutes = [
 ['command_center', 'Today', 'Command Center', 'Overview', 'today'],
 ['morning_report', 'Today', 'Morning Report', 'Changes', 'today'],
 ['daily_workflow', 'Today', 'Daily Workflow', 'Preparation', 'today'],
 ['relative_strength', 'Markets', 'Relative Strength', 'Relative Strength', 'research'],
 ['spx_nq_futures', 'Markets', 'SPX / NQ Futures', 'ES / NQ Context', 'research'],
 ['sector_rotation', 'Markets', 'Sector Rotation', 'Sector Archive', 'research'],
 ['scan', 'Scanner', 'Scanner', 'Scanner', 'opportunities'],
 ['broad_watchlist', 'Scanner', 'Broad Watchlist', 'Broad Watchlist', 'opportunities'],
 ['heatmap', 'Scanner', 'Heatmap', 'Heatmap', 'opportunities'],
 ['ticker_history', 'Research', 'Ticker History', 'Instrument', 'research'],
 ['options_ideas', 'Research', 'Options Ideas', 'Options Ideas', 'research'],
 ['options_flow', 'Research', 'Options Flow', 'Options Flow', 'research'],
 ['liquidity_map', 'Research', 'Liquidity Map', 'Liquidity Map', 'research'],
 ['backtest', 'Research', 'Backtest', 'Backtest', 'research'],
 ['strategy_lab', 'Research', 'Strategy Lab', 'Strategy Lab', 'research'],
 ['idea_tracking', 'Journal', 'Idea Tracking', 'Idea Tracking', 'portfolio'],
 ['journal', 'Journal', 'Outcome Journal', 'Outcome Journal', null],
 ['data_cache', 'System', 'Data Cache', 'Data Cache', 'system'],
 ['schwab', 'System', 'Schwab API', 'Schwab API', 'system'],
 ['jobs', 'System', 'Jobs', 'Jobs', 'system'],
 ['run_history', 'System', 'Run History', 'Run History', 'system'],
 ['strategy_rules', 'System', 'Strategy Rules', 'Strategy Rules', 'system'],
].map(([page, workspace, title, label, targetPage]) => ({
 page, workspace, title, label, surface: page, legacy: true, targetPage,
}));

export const workspaceRoutes = [...primaryWorkspaceRoutes, ...legacyWorkspaceRoutes];

export const routeAliases = {
 qx: ['scan'], scanner: ['scan'], watchlist: ['broad_watchlist'], spx_dashboard: ['spx_nq_futures'],
 liquidity: ['liquidity_map'], performance: ['idea_tracking'],
 pipeline: ['jobs', 'job_view', 'Pipeline'], pipeline_control: ['jobs', 'job_view', 'Pipeline'],
 automation_control: ['jobs', 'job_view', 'Schedule'], history: ['run_history', 'history_view', 'Scans'],
 workflow_history: ['run_history', 'history_view', 'Workflows'],
 command_snapshots: ['run_history', 'history_view', 'Snapshots'],
};

export const workspaceHomes = primaryWorkspaceRoutes;

export function resolveWorkspaceRoute(page = 'relative_strength') {
 const key = page.trim().replace(/^\/+|\/+$/g, '') || 'relative_strength';
 const [canonical, viewKey, view] = Object.hasOwn(routeAliases, key) ? routeAliases[key] : [key];
 const route = workspaceRoutes.find(item => item.page === canonical);
 return route ? {...route, ...(viewKey ? {[viewKey]: view} : {})} : null;
}
