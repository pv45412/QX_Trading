import {adaptQxV2Evaluation, lifecycleStates} from './qx-v2-adapter.js';

export const opportunityStates = [...lifecycleStates];

export function canonicalOpportunityFromEvaluation(payload, {horizon = 'DAY', fixtureState = null} = {}) {
  const canonical = adaptQxV2Evaluation(payload);
  if (!canonical || !lifecycleStates.includes(canonical.state)) return null;
  return {
    sourceType: 'CANONICAL',
    symbol: canonical.symbol,
    horizon,
    timeframe: canonical.timeframe,
    evaluationId: canonical.evaluationId,
    evaluationTimestamp: canonical.evaluationTimestamp,
    pipelineVersion: canonical.pipelineVersion,
    publicationState: canonical.publicationState,
    state: canonical.state,
    direction: canonical.directionLabel,
    playbook: canonical.playbook,
    marketDriver: canonical.marketDriver?.primary_driver?.label || (canonical.marketDriver?.status && canonical.marketDriver.status !== 'UNAVAILABLE' ? canonical.marketDriver.status : 'UNAVAILABLE'),
    marketDriverData: canonical.marketDriver ?? null,
    trigger: canonical.trigger,
    triggerSource: canonical.triggerSource,
    invalidation: canonical.invalidation,
    tradeability: canonical.tradeabilitySummary.state,
    optionsSuitability: canonical.optionsSummary.state,
    portfolioRisk: canonical.portfolioSummary.state,
    evidenceCoverage: canonical.evidenceCoverage,
    coverageStatus: canonical.coverageStatus,
    dependencies: canonical.dependencies,
    reasonCodes: canonical.reasons,
    evidence: canonical.evidence,
    fixtureState,
  };
}

export function canonicalOpportunityFromRecord(payload, {horizon = 'DAY'} = {}) {
  if (!payload || payload.source_mode !== 'LIVE' || !lifecycleStates.includes(payload.lifecycle_state)) return null;
  const dependencies = Object.entries(payload.data_dependencies || {}).map(([name, dependency]) => ({
    name,
    available: dependency?.available === true,
    source: dependency?.source ?? null,
    dataAsOf: dependency?.data_as_of ?? null,
    retrievedAt: dependency?.retrieved_at ?? null,
    freshness: dependency?.freshness ?? null,
    publicationState: dependency?.publication_state ?? null,
    syncStatus: dependency?.sync_status ?? null,
  }));
  return {
    sourceType: 'CANONICAL',
    symbol: text(payload.symbol),
    horizon,
    timeframe: text(payload.timeframe),
    evaluationId: payload.evaluation_id ?? null,
    evaluationTimestamp: payload.evaluation_timestamp ?? null,
    pipelineVersion: payload.pipeline_version ?? null,
    publicationState: payload.publication_state ?? null,
    state: payload.lifecycle_state,
    direction: payload.direction ?? null,
    playbook: payload.primary_playbook_id ?? null,
    marketDriver: payload.market_driver?.primary_driver?.label || (payload.market_driver?.status && payload.market_driver.status !== 'UNAVAILABLE' ? payload.market_driver.status : 'UNAVAILABLE'),
    marketDriverData: payload.market_driver ?? null,
    trigger: finiteOrNull(payload.trigger),
    triggerSource: payload.trigger_source ?? null,
    invalidation: finiteOrNull(payload.invalidation),
    tradeability: payload.tradeability_state ?? null,
    optionsSuitability: payload.options_state ?? null,
    portfolioRisk: payload.portfolio_state ?? null,
    evidenceCoverage: finiteOrNull(payload.evidence_coverage),
    coverageStatus: payload.coverage_status ?? null,
    dependencies,
    reasonCodes: Array.isArray(payload.reason_codes) ? [...payload.reason_codes] : [],
    evidence: [],
    fixtureState: null,
  };
}

export function canonicalOpportunitiesFromResponse(payload, {horizon = 'DAY'} = {}) {
  if (!payload || payload.source_mode !== 'LIVE' || !Array.isArray(payload.items)) return [];
  return payload.items
    .map(item => canonicalOpportunityFromRecord(item, {horizon}))
    .filter(Boolean);
}

export function legacyDiscoveryFromMovers(payload) {
  if (!payload) return [];
  const rows = Array.isArray(payload.rows)
    ? payload.rows
    : uniqueRankedMovers(payload.groups);
  return rows.map(row => ({
    sourceType: 'LEGACY',
    symbol: text(row.symbol ?? row.etf),
    name: text(row.name),
    sector: text(row.sector),
    industry: text(row.industry),
    nameSource: text(row.name_source),
    sectorSource: text(row.sector_source),
    asOf: row.as_of ?? payload.market_as_of ?? payload.retrieved_at ?? null,
    return1d: finiteOrNull(row.return_1d ?? row.return),
    excess1d: finiteOrNull(row.excess_1d),
    lastPrice: finiteOrNull(row.last),
    netChange: finiteOrNull(row.change),
    volume: finiteOrNull(row.volume),
    benchmarkSymbol: text(row.benchmark_symbol || payload.benchmark?.symbol),
    benchmarkReturn1d: finiteOrNull(row.benchmark_return_1d ?? payload.benchmark?.return_1d),
    benchmarkSource: text(row.benchmark_source || payload.benchmark?.source),
    source: text(row.source || payload.source),
    freshness: text(row.freshness || payload.freshness || 'CURRENT_REQUEST'),
  })).filter(row => row.symbol);
}

export function filterCanonicalOpportunities(rows, filters = {}) {
  const query = text(filters.query).toUpperCase();
  const filtered = rows.filter(row => (
    (!filters.horizon || row.horizon === filters.horizon)
    && (!filters.state || filters.state === 'ALL' || (filters.state === 'ACTIVE' ? !terminalStates.has(row.state) : row.state === filters.state))
    && (!filters.direction || filters.direction === 'ALL' || (row.direction || 'UNAVAILABLE') === filters.direction)
    && (!query || [row.symbol, row.playbook, row.state, row.direction].some(value => text(value).toUpperCase().includes(query)))
  ));
  return sortRows(filtered, filters.sort);
}

const terminalStates = new Set([
  'BLOCKED',
  'NO_SETUP',
  'NOT_TRADEABLE',
  'OPTIONS_NOT_SUITABLE',
  'PORTFOLIO_VETOED',
  'EXPIRED',
]);

function uniqueRankedMovers(groups) {
  if (!groups || typeof groups !== 'object') return [];
  const unique = new Map();
  for (const row of [...(groups.highest || []), ...(groups.lowest || [])]) {
    const symbol = text(row?.symbol).toUpperCase();
    if (symbol && !unique.has(symbol)) unique.set(symbol, row);
  }
  return [...unique.values()];
}

export function filterLegacyDiscovery(rows, filters = {}) {
  const query = text(filters.query).toUpperCase();
  const filtered = rows.filter(row => !query || [row.symbol, row.name, row.sector].some(value => text(value).toUpperCase().includes(query)));
  return sortRows(filtered, filters.sort);
}

export function tradeHandoffUpdates(row) {
  return {
    symbol: row.symbol,
    horizon: row.horizon,
    timeframe: row.timeframe,
    evaluation_timestamp: row.evaluationTimestamp ?? '',
    evaluation_id: row.evaluationId ?? '',
  };
}

function sortRows(rows, sort = 'evaluation_desc') {
  const result = [...rows];
  if (sort === 'symbol') return result.sort((left, right) => left.symbol.localeCompare(right.symbol));
  if (sort === 'state') return result.sort((left, right) => text(left.state).localeCompare(text(right.state)) || left.symbol.localeCompare(right.symbol));
  if (sort === 'return_desc') return result.sort((left, right) => compareNullable(right.return1d, left.return1d) || left.symbol.localeCompare(right.symbol));
  return result.sort((left, right) => compareNullable(Date.parse(right.evaluationTimestamp), Date.parse(left.evaluationTimestamp)) || left.symbol.localeCompare(right.symbol));
}

function compareNullable(left, right) {
  const leftFinite = Number.isFinite(left);
  const rightFinite = Number.isFinite(right);
  if (leftFinite && rightFinite) return left - right;
  if (leftFinite) return -1;
  if (rightFinite) return 1;
  return 0;
}

function finiteOrNull(value) {
  if (value == null || typeof value === 'boolean' || (typeof value === 'string' && value.trim() === '')) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function text(value) {
  return typeof value === 'string' ? value : '';
}
