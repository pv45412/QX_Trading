// Canonical React destinations; parity tests check the Streamlit page registry.
export const workspaceRoutes = [
 ['command_center', 'Today', 'Command Center', 'Overview'],
 ['morning_report', 'Today', 'Morning Report', 'Changes'],
 ['daily_workflow', 'Today', 'Daily Workflow', 'Preparation'],
 ['relative_strength', 'Markets', 'Relative Strength', 'Relative Strength'],
 ['spx_nq_futures', 'Markets', 'SPX / NQ Futures', 'ES / NQ Context'],
 ['sector_rotation', 'Markets', 'Sector Rotation', 'Sector Archive'],
 ['scan', 'Scanner', 'Scanner', 'Scanner'],
 ['broad_watchlist', 'Scanner', 'Broad Watchlist', 'Broad Watchlist'],
 ['heatmap', 'Scanner', 'Heatmap', 'Heatmap'],
 ['ticker_history', 'Research', 'Ticker History', 'Instrument'],
 ['options_ideas', 'Research', 'Options Ideas', 'Options Ideas'],
 ['options_flow', 'Research', 'Options Flow', 'Options Flow'],
 ['liquidity_map', 'Research', 'Liquidity Map', 'Liquidity Map'],
 ['backtest', 'Research', 'Backtest', 'Backtest'],
 ['strategy_lab', 'Research', 'Strategy Lab', 'Strategy Lab'],
 ['idea_tracking', 'Journal', 'Idea Tracking', 'Idea Tracking'],
 ['journal', 'Journal', 'Outcome Journal', 'Outcome Journal'],
 ['data_cache', 'System', 'Data Cache', 'Data Cache'],
 ['schwab', 'System', 'Schwab API', 'Schwab API'],
 ['jobs', 'System', 'Jobs', 'Jobs'],
 ['run_history', 'System', 'Run History', 'Run History'],
 ['strategy_rules', 'System', 'Strategy Rules', 'Strategy Rules'],
].map(([page, workspace, title, label]) => ({page, workspace, title, label}));

export const routeAliases = {
 qx: ['scan'], scanner: ['scan'], watchlist: ['broad_watchlist'], spx_dashboard: ['spx_nq_futures'],
 liquidity: ['liquidity_map'], performance: ['idea_tracking'],
 pipeline: ['jobs', 'job_view', 'Pipeline'], pipeline_control: ['jobs', 'job_view', 'Pipeline'],
 automation_control: ['jobs', 'job_view', 'Schedule'], history: ['run_history', 'history_view', 'Scans'],
 workflow_history: ['run_history', 'history_view', 'Workflows'],
 command_snapshots: ['run_history', 'history_view', 'Snapshots'],
};

export const workspaceHomes = workspaceRoutes.filter((route, index, routes) =>
 routes.findIndex(other => other.workspace === route.workspace) === index);

export function resolveWorkspaceRoute(page = 'relative_strength') {
 const key = page.trim().replace(/^\/+|\/+$/g, '') || 'relative_strength';
 const [canonical, viewKey, view] = Object.hasOwn(routeAliases, key) ? routeAliases[key] : [key];
 const route = workspaceRoutes.find(item => item.page === canonical);
 return route ? {...route, ...(viewKey ? {[viewKey]: view} : {})} : null;
}
