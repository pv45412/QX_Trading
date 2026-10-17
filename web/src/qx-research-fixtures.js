export function researchSnapshotFixture(symbol = 'NVDA') {
  return {symbol, status: 'SOURCE_BACKED', last_price: 181.25, as_of: '2026-09-16T20:00:00Z', data_as_of: '2026-09-16T20:00:00Z',
    retrieved_at: '2026-09-16T20:01:00Z', source: 'fixture_cache', source_class: 'SOURCE_BACKED',
    structure: {current_trend: 'BEARISH', structure_score: 62.5, latest_bos: 'BEARISH_BOS', latest_choch: 'BEARISH_CHOCH', active_fvgs: []}};
}

export function researchAnalyticsFixture() {
  const rows = [
    row('XLK', 'Information Technology', .042, 92, 0, .08),
    row('XLE', 'Energy', -.018, 24, 12, -.01),
    row('XLF', 'Financials', .011, 64, 4, .02),
  ];
  return {rows, coverage: rows.length, universe: rows.length, benchmark: 'SPY', benchmark_metrics: {as_of: '2026-09-16T20:00:00Z'}};
}

export function researchLineFixture(symbol = 'XLK') {
  return {symbol, benchmark: 'SPY', status: 'CACHED_UNVERIFIED', as_of: '2026-09-16T20:00:00Z', sector_source: 'fixture_cache', benchmark_source: 'fixture_cache',
    points: [{date: '2026-09-12T20:00:00Z', ratio: .41}, {date: '2026-09-15T20:00:00Z', ratio: .415}, {date: '2026-09-16T20:00:00Z', ratio: .419}],
    summary: {current_rs: .419, rs_high: .419, rs_change: .021, correction: null}};
}

export function researchHoldingsFixture(symbol = 'XLK') {
  return {symbol, source: 'fixture_fund_source', retrieved_at: '2026-09-16T20:01:00Z', holdings_as_of: '2026-09-15', holdings_status: 'SAVED_UNVERIFIED', stale_holdings: true, analytics_coverage: 2,
    rows: [holding('NVDA', 'NVIDIA', .18, .05), holding('MSFT', 'Microsoft', .16, .02), holding('AAPL', 'Apple', .14, -.01)]};
}

export function researchOptionsFixture() {
  return {ideas: [idea('NVDA', 'BULLISH', 'LEAP_CALL'), idea('TSLA', 'BEARISH', 'CREDIT_SPREAD')]};
}

export function researchStrategyFixture() {
  return {strategy_name: 'Bull Call Debit Spread', category: 'Directional Expansion', compatibility_score: 71, ideal_iv_rank: 'Modeled input', description: 'Hypothetical payoff workspace.',
    preset_legs: [{option_type: 'call', action: 'buy', strike: 175, premium: 8, quantity: 1, dte: 45}, {option_type: 'call', action: 'sell', strike: 190, premium: 3, quantity: 1, dte: 45}]};
}

export function researchPayoffFixture() {
  return {net_debit_credit: 500, max_risk_dollars: 500, max_profit_dollars: 1000, breakevens: [180], curve: [
    {underlying_price: 150, pnl_dollars: -500}, {underlying_price: 180, pnl_dollars: 0}, {underlying_price: 210, pnl_dollars: 1000},
  ]};
}

export function researchBacktestFixture(symbol = 'NVDA') {
  return {symbol, total_trades: 12, win_rate: .5, average_return_pct: .012, trades: []};
}

function row(etf, sector, rs_change, rs_rank, days_off_high, correction_excess) {
  return {etf, sector, status: 'CACHED_UNVERIFIED', source: 'fixture_cache', as_of: '2026-09-16T20:00:00Z', rs_change, rs_rank,
    days_off_high, correction_excess, mtd: rs_change / 2, rs_days: 12, up_down: .55, up_days: 6, down_days: 11, corr_qqq: .75, corr_dia: .61,
    correction: {start: '2026-08-20T20:00:00Z', end: '2026-08-28T20:00:00Z'}};
}

function holding(symbol, name, weight, rsChange) {
  return {symbol, name, weight, analytics: {rs_change: rsChange, rs_days: 12, up_down: .55, up_days: 6, down_days: 11, as_of: '2026-09-16T20:00:00Z'}};
}

function idea(symbol, trend_bias, category) {
  return {symbol, name: symbol, trend_bias, category, price: 180, strategy_name: category === 'LEAP_CALL' ? 'Modeled LEAP Call' : 'Modeled Credit Spread', contract: `${symbol} hypothetical`,
    value_for_money_score: 72, capital_saved_pct: 55, capital_required: 4500, stock_purchase_cost: 18000, option_price: 45, delta: .7, iv: .3, rv: .25,
    vol_classification: 'MODELED', why_better_value: ['Hypothetical comparison for research only.']};
}
