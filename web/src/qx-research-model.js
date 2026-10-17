export const researchModes = [
  {id: 'symbol', label: 'Symbol', shortLabel: 'Symbol'},
  {id: 'etf_sector', label: 'ETF / Sector', shortLabel: 'ETF'},
  {id: 'relative_strength', label: 'Relative Strength / Rotation', shortLabel: 'RS / Rotation'},
  {id: 'options_strategy', label: 'Options / Strategy Research', shortLabel: 'Options'},
  {id: 'historical', label: 'Historical / Backtest', shortLabel: 'Historical'},
  {id: 'long_term', label: 'Long-Term Thesis', shortLabel: 'Long-Term'},
];

const validModes = new Set(researchModes.map(mode => mode.id));
const legacyModeMap = {
  ticker_history: 'symbol',
  relative_strength: 'relative_strength',
  sector_rotation: 'relative_strength',
  options_ideas: 'options_strategy',
  options_flow: 'options_strategy',
  strategy_lab: 'options_strategy',
  liquidity_map: 'historical',
  backtest: 'historical',
  spx_nq_futures: 'historical',
};

export function researchModeForRoute(page, requestedMode) {
  if (page === 'research' && validModes.has(requestedMode)) return requestedMode;
  return legacyModeMap[page] || 'symbol';
}

export function buildResearchSnapshot(payload, requestedSymbol) {
  if (!payload || typeof payload !== 'object') return unavailableSnapshot(requestedSymbol, 'RESEARCH_SNAPSHOT_UNAVAILABLE');
  const available = payload.status !== 'UNAVAILABLE' && payload.source_class === 'SOURCE_BACKED';
  return {
    symbol: text(payload.symbol) || requestedSymbol || null,
    status: available ? payload.status : 'UNAVAILABLE',
    sourceClass: payload.source_class ?? 'UNAVAILABLE',
    source: available ? payload.source ?? null : null,
    dataAsOf: available ? payload.data_as_of ?? payload.as_of ?? null : null,
    retrievedAt: payload.retrieved_at ?? null,
    lastPrice: available ? finiteOrNull(payload.last_price) : null,
    trend: available ? payload.structure?.current_trend ?? null : null,
    structureScore: available ? finiteOrNull(payload.structure?.structure_score) : null,
    latestBos: available ? payload.structure?.latest_bos ?? null : null,
    latestChoch: available ? payload.structure?.latest_choch ?? null : null,
    activeFvgCount: available && Array.isArray(payload.structure?.active_fvgs) ? payload.structure.active_fvgs.length : null,
    reasonCode: payload.reason_code ?? (available ? null : 'RESEARCH_SNAPSHOT_UNAVAILABLE'),
  };
}

export function buildBacktestView(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const result = Array.isArray(payload.results) ? payload.results[0] : payload;
  return {
    symbol: text(result?.symbol) || null,
    totalTrades: integerOrNull(result?.total_trades),
    winRate: finiteOrNull(result?.win_rate),
    averageReturnPct: finiteOrNull(result?.average_return_pct),
    trades: Array.isArray(result?.trades) ? result.trades.map(trade => ({
      entryPrice: finiteOrNull(trade.entry_price),
      exitPrice: finiteOrNull(trade.exit_price),
      outcome: text(trade.outcome),
      returnPct: finiteOrNull(trade.return_pct),
      setupScore: finiteOrNull(trade.setup_score),
    })) : [],
  };
}

function unavailableSnapshot(symbol, reasonCode) {
  return {symbol: symbol || null, status: 'UNAVAILABLE', sourceClass: 'UNAVAILABLE', source: null,
    dataAsOf: null, retrievedAt: null, lastPrice: null, trend: null, structureScore: null,
    latestBos: null, latestChoch: null, activeFvgCount: null, reasonCode};
}

function finiteOrNull(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function integerOrNull(value) {
  return Number.isInteger(value) ? value : null;
}

function text(value) {
  return typeof value === 'string' && value.trim() ? value : null;
}
