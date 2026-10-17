import {createQxV2PreviewFixture} from './qx-v2-fixtures.js';

export const portfolioFixtureStates = [
  'healthy',
  'partial',
  'stale',
  'sector_unknown',
  'greeks_unavailable',
  'approved',
  'vetoed',
  'no_account',
];

export function createPortfolioFixture(state = 'healthy') {
  const normalized = portfolioFixtureStates.includes(state) ? state : 'healthy';
  if (normalized === 'no_account') return {snapshot: unavailableSnapshot(), evaluation: null};
  const snapshot = baseSnapshot();
  let evaluation = null;
  if (normalized === 'partial') {
    snapshot.status = 'PARTIAL';
    snapshot.sync_status = 'PARTIAL';
    snapshot.pnl_status = 'PARTIAL';
    snapshot.daily_unrealized_pnl = null;
    snapshot.total_unrealized_pnl = null;
    snapshot.reason_codes = ['PARTIAL_ACCOUNT_EVIDENCE', 'PNL_EVIDENCE_INCOMPLETE'];
  }
  if (normalized === 'stale') {
    snapshot.status = 'STALE';
    snapshot.freshness = 'STALE_BLOCKED';
    snapshot.reason_codes = ['ACCOUNT_DATA_STALE'];
  }
  if (normalized === 'sector_unknown') {
    snapshot.status = 'PARTIAL';
    snapshot.sync_status = 'PARTIAL';
    snapshot.sector_status = 'UNKNOWN';
    snapshot.sector_allocations = [];
    snapshot.positions[1] = {...snapshot.positions[1], canonical_sector_id: null, provider_sector_raw: null, sector_status: 'UNKNOWN'};
    snapshot.reason_codes = ['PARTIAL_ACCOUNT_EVIDENCE', 'SECTOR_PROVENANCE_INCOMPLETE'];
  }
  if (normalized === 'greeks_unavailable') {
    snapshot.status = 'PARTIAL';
    snapshot.greeks = null;
    snapshot.greeks_status = 'UNAVAILABLE';
    snapshot.positions = snapshot.positions.map(position => ({...position, delta: null, gamma: null, theta: null, vega: null, greeks_status: 'UNAVAILABLE'}));
    snapshot.reason_codes = ['GREEKS_UNAVAILABLE'];
  }
  if (normalized === 'approved' || normalized === 'vetoed') {
    const lifecycle = normalized === 'approved' ? 'PORTFOLIO_APPROVED' : 'PORTFOLIO_VETOED';
    evaluation = createQxV2PreviewFixture(lifecycle, 'NVDA');
    evaluation.evaluation_id = `fixture-day-${normalized}-nvda`;
    evaluation.portfolio_risk = {
      ...evaluation.portfolio_risk,
      symbol: 'NVDA',
      max_loss_per_contract: 240,
      candidate_total_max_loss: 480,
      candidate_buying_power_required: 480,
      symbol_exposure_before: 19500,
      symbol_exposure_after: 19980,
      sector_exposure_before: 42950,
      sector_exposure_after: 43430,
      portfolio_delta_before: 312.5,
      portfolio_delta_after: 398.5,
      portfolio_gamma_before: 0,
      portfolio_gamma_after: 4.2,
      portfolio_theta_before: 0,
      portfolio_theta_after: -31.4,
      portfolio_vega_before: 0,
      portfolio_vega_after: 58.7,
    };
  }
  return {snapshot, evaluation};
}

function baseSnapshot() {
  const dataAsOf = '2026-09-16T14:35:00Z';
  return {
    request_started_at: '2026-09-16T14:34:58Z',
    evaluation_timestamp: dataAsOf,
    pipeline_version: 'core_v1',
    publication_state: 'RESEARCH_ONLY',
    status: 'COMPLETE',
    read_only: true,
    account_id: 'qxacct_fixture_safe_1',
    equity: 150000,
    cash: 42000,
    buying_power: 76000,
    daily_realized_pnl: 185,
    daily_unrealized_pnl: -240,
    total_unrealized_pnl: 4850,
    pnl_status: 'AVAILABLE',
    open_orders_count: 1,
    gross_market_exposure: 68950,
    net_market_exposure: 68950,
    positions: [
      position('AAPL', 100, 182, 190, 19000, 800, 12.6667, 'XLK', 'Information Technology'),
      position('NVDA', 150, 118, 130, 19500, 1800, 13, 'XLK', 'Information Technology'),
      position('JPM', 125, 196, 203.6, 25450, 950, 16.9667, 'XLF', 'Financial Services'),
      position('XOM', 50, 96, 100, 5000, 200, 3.3333, 'XLE', 'Energy'),
    ],
    greeks: {net_delta: 425, net_gamma: 0, net_theta: 0, net_vega: 0, beta_weighted_delta: 0},
    greeks_status: 'AVAILABLE',
    sector_allocations: [
      {sector: 'XLK', allocation_pct: 25.6667, market_value: 38500, is_overconcentrated: false},
      {sector: 'XLF', allocation_pct: 16.9667, market_value: 25450, is_overconcentrated: false},
      {sector: 'XLE', allocation_pct: 3.3333, market_value: 5000, is_overconcentrated: false},
    ],
    sector_status: 'KNOWN',
    sector_mapping_source: 'qx_canonical_sector_taxonomy',
    sector_mapping_version: 'research_v1',
    data_as_of: dataAsOf,
    retrieved_at: dataAsOf,
    snapshot_id: 42,
    freshness: 'FRESH',
    sync_status: 'SYNCED',
    source: 'fixture_read_only_account',
    reason_codes: [],
    dependency: {name: 'account_snapshot', available: true, source: 'fixture_read_only_account', freshness: 'FRESH', publication_state: 'RESEARCH_ONLY', sync_status: 'SYNCED', data_as_of: dataAsOf},
    provider_latency_ms: 18.4,
  };
}

function position(symbol, quantity, entry, current, marketValue, pnl, concentration, sector, providerSector) {
  return {
    symbol, asset_class: 'STOCK', quantity, entry_price: entry, current_price: current,
    market_value: marketValue, unrealized_pnl: pnl, unrealized_pnl_pct: (pnl / (quantity * entry)) * 100,
    concentration_pct: concentration, canonical_sector_id: sector, provider_sector_raw: providerSector,
    sector_status: 'KNOWN', sector_mapping_source: 'qx_canonical_sector_taxonomy',
    sector_mapping_version: 'research_v1', delta: quantity, gamma: 0, theta: 0, vega: 0,
    greeks_status: 'AVAILABLE',
  };
}

function unavailableSnapshot() {
  return {
    request_started_at: '2026-09-16T14:34:58Z', evaluation_timestamp: '2026-09-16T14:35:00Z',
    pipeline_version: 'core_v1', publication_state: 'BLOCKED', status: 'UNAVAILABLE', read_only: true,
    account_id: null, equity: null, cash: null, buying_power: null, daily_realized_pnl: null,
    daily_unrealized_pnl: null, total_unrealized_pnl: null, pnl_status: 'UNAVAILABLE',
    open_orders_count: null, gross_market_exposure: null, net_market_exposure: null,
    positions: [], greeks: null, greeks_status: 'UNAVAILABLE', sector_allocations: [], sector_status: 'UNAVAILABLE',
    data_as_of: null, retrieved_at: null, snapshot_id: null, freshness: 'UNAVAILABLE', sync_status: 'UNAVAILABLE',
    source: null, reason_codes: ['ACCOUNT_SNAPSHOT_UNAVAILABLE'],
    dependency: {name: 'account_snapshot', available: false, publication_state: 'BLOCKED', reason_code: 'ACCOUNT_SNAPSHOT_UNAVAILABLE'},
    provider_latency_ms: null,
  };
}
