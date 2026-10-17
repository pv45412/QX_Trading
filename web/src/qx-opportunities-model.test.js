import test from 'node:test';
import assert from 'node:assert/strict';
import {createQxV2PreviewFixture} from './qx-v2-fixtures.js';
import {normalizeCanonicalOpportunityList} from './qx-opportunities-client.js';
import {
  canonicalOpportunityFromEvaluation,
  canonicalOpportunityFromRecord,
  filterCanonicalOpportunities,
  legacyDiscoveryFromMovers,
  tradeHandoffUpdates,
} from './qx-opportunities-model.js';

test('canonical opportunity preserves lifecycle fields without rescoring', () => {
  const payload = createQxV2PreviewFixture('TRADEABLE', 'NVDA');
  payload.evaluation_id = 'eval-123';
  payload.direction.direction_score = 0;
  payload.direction.direction_evidence_coverage = 0;
  const row = canonicalOpportunityFromEvaluation(payload, {horizon: 'SWING'});
  assert.equal(row.state, 'TRADEABLE');
  assert.equal(row.direction, 'BULLISH');
  assert.equal(row.evidenceCoverage, 0);
  assert.equal(row.evaluationId, 'eval-123');
  assert.equal(row.marketDriver, 'UNAVAILABLE');
  assert.equal(Object.hasOwn(row, 'score'), false);
});

test('partial downstream values remain unavailable while upstream evidence survives', () => {
  const row = canonicalOpportunityFromEvaluation(createQxV2PreviewFixture('ARMED', 'SPY'), {horizon: 'DAY'});
  assert.equal(row.state, 'ARMED');
  assert.equal(row.trigger, 450);
  assert.equal(row.triggerSource, 'UNCONFIRMED');
  assert.equal(row.tradeability, null);
  assert.equal(row.portfolioRisk, null);
});

test('legacy discovery never receives canonical labels or inferred fields', () => {
  const rows = legacyDiscoveryFromMovers({rows: [{etf: 'AMD', name: 'AMD', return_1d: 0, excess_1d: null, as_of: '', source: 'schwab'}]});
  assert.deepEqual(rows, [{
    sourceType: 'LEGACY', symbol: 'AMD', name: 'AMD', sector: '', asOf: '', return1d: 0,
    industry: '', nameSource: '', sectorSource: '', excess1d: null, lastPrice: null,
    netChange: null, volume: null, benchmarkSymbol: '', benchmarkReturn1d: null,
    benchmarkSource: '', source: 'schwab', freshness: 'CURRENT_REQUEST',
  }]);
  assert.equal(Object.hasOwn(rows[0], 'state'), false);
  assert.equal(Object.hasOwn(rows[0], 'trigger'), false);
  assert.equal(Object.hasOwn(rows[0], 'score'), false);
});

test('live ranked movers are deduplicated with retrieval provenance', () => {
  const rows = legacyDiscoveryFromMovers({
    source: 'schwab',
    retrieved_at: '2026-09-17T18:30:00Z',
    groups: {
      highest: [{symbol: 'AMD', return: 0.04}],
      lowest: [{symbol: 'AMD', return: 0.04}, {symbol: 'T', return: -0.02}],
    },
  });
  assert.deepEqual(rows.map(row => row.symbol), ['AMD', 'T']);
  assert.equal(rows[0].asOf, '2026-09-17T18:30:00Z');
  assert.equal(rows[0].return1d, 0.04);
  assert.equal(rows[0].source, 'schwab');
  assert.equal(rows[0].freshness, 'CURRENT_REQUEST');
});

test('live mover enrichment preserves metadata and benchmark provenance', () => {
  const [row] = legacyDiscoveryFromMovers({
    source: 'schwab',
    benchmark: {symbol: 'SPY', return_1d: 0.01, source: 'schwab'},
    rows: [{
      symbol: 'AAPL', name: 'APPLE INC', name_source: 'schwab:movers.description',
      sector: 'Information Technology', industry: 'Technology Hardware',
      sector_source: 'local_symbol_metadata_cache', return_1d: 0.025,
      excess_1d: 0.015, last: 250, change: 6, volume: 1000,
      benchmark_symbol: 'SPY', benchmark_return_1d: 0.01,
      benchmark_source: 'schwab:quote:SPY', source: 'schwab',
    }],
  });

  assert.equal(row.name, 'APPLE INC');
  assert.equal(row.sector, 'Information Technology');
  assert.equal(row.industry, 'Technology Hardware');
  assert.equal(row.excess1d, 0.015);
  assert.equal(row.lastPrice, 250);
  assert.equal(row.benchmarkSource, 'schwab:quote:SPY');
});

test('ACTIVE lifecycle filter excludes terminal evaluated outcomes', () => {
  const rows = [
    {symbol: 'SPY', horizon: 'DAY', state: 'WATCH'},
    {symbol: 'QQQ', horizon: 'DAY', state: 'NO_SETUP'},
    {symbol: 'IWM', horizon: 'DAY', state: 'BLOCKED'},
  ];
  assert.deepEqual(
    filterCanonicalOpportunities(rows, {horizon: 'DAY', state: 'ACTIVE'}).map(row => row.symbol),
    ['SPY'],
  );
});

test('horizon filtering is context only and does not rewrite lifecycle state', () => {
  const day = canonicalOpportunityFromEvaluation(createQxV2PreviewFixture('WATCH', 'SPY'), {horizon: 'DAY'});
  const swing = {...day, horizon: 'SWING'};
  assert.deepEqual(filterCanonicalOpportunities([day, swing], {horizon: 'SWING'}), [swing]);
  assert.equal(swing.state, day.state);
  assert.equal(swing.direction, day.direction);
});

test('Trade handoff preserves available evaluation context exactly', () => {
  const updates = tradeHandoffUpdates({
    symbol: 'QQQ', horizon: 'INVEST', timeframe: '1d',
    evaluationTimestamp: '2026-09-16T14:35:00Z', evaluationId: 'eval-qqq-9',
  });
  assert.deepEqual(updates, {
    symbol: 'QQQ', horizon: 'INVEST', timeframe: '1d',
    evaluation_timestamp: '2026-09-16T14:35:00Z', evaluation_id: 'eval-qqq-9',
  });
});

test('missing evaluation identity remains missing instead of being fabricated', () => {
  const row = canonicalOpportunityFromEvaluation(createQxV2PreviewFixture('NO_SETUP', 'XOM'), {horizon: 'DAY'});
  assert.equal(row.evaluationId, null);
  assert.equal(tradeHandoffUpdates(row).evaluation_id, '');
});

test('persisted LIVE record maps without lifecycle inference', () => {
  const row = canonicalOpportunityFromRecord({
    source_mode: 'LIVE',
    evaluation_id: 'qxev1_00000000000070008000000000000001',
    symbol: 'SPY',
    timeframe: '5m',
    evaluation_timestamp: '2026-09-16T14:30:00Z',
    pipeline_version: 'core_v1',
    publication_state: 'RESEARCH_ONLY',
    lifecycle_state: 'ARMED',
    direction: 'BEARISH',
    primary_playbook_id: 'ORB',
    trigger: 500,
    invalidation: 503,
    evidence_coverage: 0,
    reason_codes: ['WAITING_FOR_TRIGGER'],
    data_dependencies: {bars: {available: true, freshness: 'POINT_IN_TIME'}},
  }, {horizon: 'DAY'});
  assert.equal(row.state, 'ARMED');
  assert.equal(row.evidenceCoverage, 0);
  assert.equal(row.trigger, 500);
  assert.equal(row.evaluationId, 'qxev1_00000000000070008000000000000001');
});

test('actual API list shape maps after trusted envelope normalization', () => {
  const payload = normalizeCanonicalOpportunityList({
    schema_version: 'qx.opportunity-list.v1',
    pipeline_version: 'core_v1',
    source_mode: 'LIVE',
    items: [{
      evaluation_id: 'qxev1_00000000000070008000000000000001',
      source_mode: 'LIVE',
      symbol: 'SPY',
      timeframe: '5m',
      evaluation_timestamp: '2026-09-16T14:30:00Z',
      lifecycle_state: 'ARMED',
      direction: 'BULLISH',
    }],
    next_cursor: null,
    has_more: false,
  });
  const row = canonicalOpportunityFromRecord(payload.items[0], {horizon: 'DAY'});
  assert.equal(row.symbol, 'SPY');
  assert.equal(row.state, 'ARMED');
});

test('non-LIVE record never enters canonical opportunity UI', () => {
  assert.equal(canonicalOpportunityFromRecord({source_mode: 'REPLAY', lifecycle_state: 'ARMED'}), null);
});
