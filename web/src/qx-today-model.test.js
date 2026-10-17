import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createCanonicalOpportunityFixtures} from './qx-opportunities-fixtures.js';
import {createQxV2PreviewFixture} from './qx-v2-fixtures.js';
import {activeTodayOpportunities, marketPulseFromEvaluations, materialHealthItems, portfolioAttentionFromSnapshot} from './qx-today-model.js';

test('market pulse projects canonical fields without creating an SPX fallback', () => {
  const spy = createQxV2PreviewFixture('WATCH', 'SPY');
  const pulse = marketPulseFromEvaluations({SPY: {data: spy, error: ''}});
  assert.equal(pulse[0].symbol, 'SPX');
  assert.equal(pulse[0].status, 'UNAVAILABLE');
  assert.equal(pulse[0].direction, null);
  assert.equal(pulse[1].symbol, 'SPY');
  assert.equal(pulse[1].direction, spy.direction.direction_label);
  assert.equal(pulse[1].regime, spy.market_regime.trend);
  assert.equal(pulse[1].status, 'PARTIAL');
  assert.equal(pulse[1].barSource, 'local_bar_cache');
  assert.equal(pulse[1].barDataAsOf, spy.evaluation_timestamp);
  assert.equal(pulse[1].barFreshness, 'POINT_IN_TIME');
  assert.equal(pulse[2].status, 'UNAVAILABLE');
});

test('market pulse projects a source-backed SPX canonical evaluation when supplied', () => {
  const spx = createQxV2PreviewFixture('NO_SETUP', 'SPX');
  const quote = {
    symbol: 'SPX', resolved_symbol: '$SPX', source: 'schwab', status: 'AVAILABLE',
    last: 6618.21, bid: 6617.9, ask: 6618.4, change_pct: -0.0042, volume: 1234,
    quote_timestamp: '2026-09-17T15:59:58Z', realtime: true, freshness: 'FRESH',
  };
  const pulse = marketPulseFromEvaluations(
    {SPX: {data: spx, error: ''}},
    {SPX: {data: quote, error: ''}},
  );
  assert.equal(pulse[0].symbol, 'SPX');
  assert.equal(pulse[0].status, 'AVAILABLE');
  assert.equal(pulse[0].direction, spx.direction.direction_label);
  assert.equal(pulse[0].publicationState, spx.publication_state);
  assert.equal(pulse[0].quoteLast, 6618.21);
  assert.equal(pulse[0].quoteBid, 6617.9);
  assert.equal(pulse[0].quoteAsk, 6618.4);
  assert.equal(pulse[0].quoteChangePct, -0.0042);
  assert.equal(pulse[0].quoteVolume, 1234);
  assert.equal(pulse[0].quoteSource, 'schwab');
  assert.equal(pulse[0].quoteRealtime, true);
  assert.equal(pulse[0].quoteTimestamp, '2026-09-17T15:59:58Z');
  assert.equal(pulse[0].quoteFreshness, 'FRESH');
  assert.equal(pulse[0].barSource, 'local_bar_cache');
  assert.equal(pulse[0].barDataAsOf, spx.evaluation_timestamp);
  assert.equal(pulse[0].barFreshness, 'POINT_IN_TIME');
});

test('market pulse preserves broker evidence when an index has no executable order book', () => {
  const spx = createQxV2PreviewFixture('NO_SETUP', 'SPX');
  const fieldEvidence = {
    last: {availability: 'AVAILABLE', source: 'schwab', reason_code: null},
    bid: {availability: 'NOT_PUBLISHED', source: 'schwab', reason_code: 'INDEX_NO_EXECUTABLE_ORDER_BOOK'},
    ask: {availability: 'NOT_PUBLISHED', source: 'schwab', reason_code: 'INDEX_NO_EXECUTABLE_ORDER_BOOK'},
    change_pct: {availability: 'AVAILABLE', source: 'schwab', reason_code: null},
    volume: {availability: 'AVAILABLE', source: 'schwab', reason_code: null},
  };
  const pulse = marketPulseFromEvaluations(
    {SPX: {data: spx, error: ''}},
    {SPX: {data: {
      symbol: 'SPX', resolved_symbol: '$SPX', asset_type: 'INDEX', source: 'schwab', status: 'AVAILABLE',
      last: 7637.76, bid: null, ask: null, change_pct: 0, volume: 2922855343,
      quote_timestamp: '2026-09-17T20:34:50.686Z', realtime: true, freshness: 'STALE',
      field_evidence: fieldEvidence,
    }, error: ''}},
  )[0];

  assert.equal(pulse.status, 'AVAILABLE');
  assert.equal(pulse.quoteBid, null);
  assert.equal(pulse.quoteAsk, null);
  assert.equal(pulse.quoteAssetType, 'INDEX');
  assert.deepEqual(pulse.quoteFieldEvidence, fieldEvidence);
});

test('market pulse keeps every missing quote and provenance field unavailable', () => {
  const spy = createQxV2PreviewFixture('WATCH', 'SPY');
  spy.data_dependencies = {};
  const pulse = marketPulseFromEvaluations(
    {SPY: {data: spy, error: ''}},
    {SPY: {data: {symbol: 'SPY', status: 'UNAVAILABLE'}, error: ''}},
  )[1];

  assert.equal(pulse.status, 'UNAVAILABLE');
  for (const field of [
    'quoteLast', 'quoteBid', 'quoteAsk', 'quoteChangePct', 'quoteVolume', 'quoteSource',
    'quoteAssetType', 'quoteFieldEvidence', 'quoteRealtime', 'quoteTimestamp', 'quoteFreshness', 'barSource', 'barDataAsOf',
    'barFreshness',
  ]) assert.equal(pulse[field], null, field);
});

test('Today pulse card keeps required live data and provenance labels visible', () => {
  const workspace = readFileSync(new URL('./QXTodayWorkspace.jsx', import.meta.url), 'utf8');
  for (const label of [
    'Bid', 'Ask', 'Volume', 'Direction', 'Regime', 'Volatility', 'Session',
    'Quote Source', 'Asset Type', 'Bid Field', 'Ask Field', 'Quote Mode', 'Quote Timestamp', 'Quote Freshness',
    'Bar Source', 'Bar Data As Of', 'Bar Freshness',
  ]) assert.match(workspace, new RegExp(`>${label}<`), label);
  for (const field of [
    'quoteLast', 'quoteChangePct', 'quoteBid', 'quoteAsk', 'quoteVolume', 'quoteSource',
    'quoteAssetType', 'quoteFieldEvidence', 'quoteRealtime', 'quoteTimestamp', 'quoteFreshness', 'barSource', 'barDataAsOf',
    'barFreshness',
  ]) assert.match(workspace, new RegExp(`item\\.${field}\\b`), field);
});

test('active opportunity ordering is presentation only and leaves rows unchanged', () => {
  const rows = createCanonicalOpportunityFixtures('SWING');
  const active = activeTodayOpportunities(rows);
  assert.deepEqual(active.map(row => row.state), ['TRIGGERED', 'TRADEABLE', 'ARMED', 'WATCH']);
  assert.equal(active.every(row => row.horizon === 'SWING'), true);
  assert.equal(active.every(row => Object.hasOwn(row, 'score') === false), true);
});

test('terminal and unavailable opportunity states are not promoted into active attention', () => {
  const active = activeTodayOpportunities(createCanonicalOpportunityFixtures('DAY'), 20);
  assert.equal(active.some(row => ['BLOCKED', 'NO_SETUP', 'OPTIONS_NOT_SUITABLE', 'PORTFOLIO_VETOED', 'PORTFOLIO_APPROVED'].includes(row.state)), false);
});

test('healthy operations do not create routine Today telemetry', () => {
  assert.deepEqual(materialHealthItems({operations: {status: 'OK', components: [{name: 'cache', status: 'OK'}]}}), []);
});

test('blocked canonical publication and degraded components remain explicit', () => {
  const blocked = createQxV2PreviewFixture('BLOCKED', 'SPY');
  const items = materialHealthItems({
    evaluations: {SPY: {data: blocked, error: ''}},
    operations: {status: 'DEGRADED', components: [{name: 'bar_cache', status: 'DEGRADED', details: 'stale'}]},
  });
  assert.equal(items.some(item => item.code === 'CANONICAL_PIPELINE_BLOCKED'), true);
  assert.equal(items.some(item => item.code === 'SYSTEM_HEALTH_DEGRADED'), true);
  assert.equal(items.some(item => item.code === 'SYSTEM_COMPONENT_DEGRADED'), true);
});

test('health items deduplicate identical fixture and canonical exceptions', () => {
  const blocked = createQxV2PreviewFixture('BLOCKED', 'SPY');
  const items = materialHealthItems({
    evaluations: {SPY: {data: blocked, error: ''}},
    fixtureItems: [{code: 'CANONICAL_PIPELINE_BLOCKED', label: 'SPY canonical pipeline blocked', detail: 'fixture', destination: 'system'}],
  });
  assert.equal(items.filter(item => item.code === 'CANONICAL_PIPELINE_BLOCKED').length, 1);
});

test('portfolio attention reports canonical partial evidence without inventing position decisions', () => {
  const attention = portfolioAttentionFromSnapshot({
    status: 'PARTIAL',
    freshness: 'FRESH',
    positions: [{symbol: 'SPY'}, {symbol: 'QQQ'}],
    reason_codes: ['SECTOR_PROVENANCE_INCOMPLETE'],
  });

  assert.deepEqual(attention, {
    status: 'PARTIAL',
    detail: '2 positions loaded; sector provenance incomplete.',
  });
});

test('portfolio attention distinguishes healthy, stale, and unavailable snapshots', () => {
  assert.equal(portfolioAttentionFromSnapshot({status: 'COMPLETE', freshness: 'FRESH', positions: [], reason_codes: []}).status, 'AVAILABLE');
  assert.equal(portfolioAttentionFromSnapshot({status: 'STALE', freshness: 'STALE_BLOCKED', positions: []}).status, 'STALE');
  assert.equal(portfolioAttentionFromSnapshot(null, 'Portfolio request failed.').status, 'UNAVAILABLE');
});
