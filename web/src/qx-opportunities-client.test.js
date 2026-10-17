import test from 'node:test';
import assert from 'node:assert/strict';
import {
  fetchLegacyOpportunityDiscovery,
  fetchCanonicalOpportunities,
  fetchCanonicalOpportunityDetail,
  normalizeCanonicalOpportunityList,
  scanCanonicalOpportunities,
} from './qx-opportunities-client.js';

test('live discovery uses guarded Schwab ranked movers request', async () => {
  let request;
  const payload = {source: 'schwab', groups: {highest: [], lowest: []}};
  const result = await fetchLegacyOpportunityDiscovery({
    fetchImpl: async (url, options) => {
      request = {url, options};
      return {ok: true, json: async () => payload};
    },
  });
  assert.equal(request.url, '/api/schwab/movers');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.headers['x-qx-refresh'], '1');
  assert.deepEqual(result, payload);
});

test('bounded scan evaluates unique symbols sequentially and reports progress', async () => {
  const requests = [];
  const progress = [];
  const results = await scanCanonicalOpportunities({
    symbols: ['spy', 'SPY', 'qqq', 'aapl'],
    timeframe: '1h',
    limit: 2,
    onProgress: value => progress.push(value),
    fetchImpl: async (url, options) => {
      requests.push({url, options});
      return {ok: true, json: async () => ({current_lifecycle_state: 'NO_SETUP'})};
    },
  });
  assert.deepEqual(requests.map(request => request.url), [
    '/api/v2/qx/evaluate/SPY?timeframe=1h',
    '/api/v2/qx/evaluate/QQQ?timeframe=1h',
  ]);
  assert.equal(requests.every(request => request.options.method === 'POST'), true);
  assert.equal(results.length, 2);
  assert.deepEqual(progress.map(value => value.completed), [1, 2]);
});

test('canonical opportunity list uses bounded read-only GET', async () => {
  let request;
  const payload = {source_mode: 'LIVE', items: []};
  const result = await fetchCanonicalOpportunities({
    timeframe: '5m',
    limit: 5,
    fetchImpl: async (url, options) => {
      request = {url, options};
      return {ok: true, json: async () => payload};
    },
  });
  assert.equal(request.url, '/api/v2/qx/opportunities?limit=5&timeframe=5m');
  assert.equal(request.options.method, undefined);
  assert.deepEqual(result, payload);
});

test('canonical store failure stays unavailable without legacy fallback', async () => {
  const requests = [];
  await assert.rejects(
    () => fetchCanonicalOpportunities({
      fetchImpl: async url => {
        requests.push(url);
        return {ok: false, status: 503};
      },
    }),
    /Canonical opportunities unavailable \(503\)/,
  );
  assert.deepEqual(requests, ['/api/v2/qx/opportunities?limit=100']);
});

test('canonical opportunity list sends supported filters and cursor deterministically', async () => {
  let request;
  await fetchCanonicalOpportunities({
    symbols: ['SPY', 'QQQ'],
    timeframe: '1h',
    states: ['ARMED', 'TRIGGERED'],
    publicationStates: ['VERIFIED'],
    direction: 'BULLISH',
    playbookId: 'ORB',
    horizonContext: 'SWING',
    includeTerminal: true,
    includeBlocked: false,
    freshOnly: true,
    cursor: 'opaque-cursor',
    limit: 25,
    fetchImpl: async (url, options) => {
      request = {url, options};
      return {ok: true, json: async () => ({source_mode: 'LIVE', items: []})};
    },
  });
  assert.equal(request.url, '/api/v2/qx/opportunities?limit=25&symbols=SPY&symbols=QQQ&timeframe=1h&states=ARMED&states=TRIGGERED&publication_states=VERIFIED&direction=BULLISH&playbook_id=ORB&horizon_context=SWING&include_terminal=true&include_blocked=false&fresh_only=true&cursor=opaque-cursor');
  assert.equal(request.options.method, undefined);
});

test('actual list envelope preserves item-level LIVE mode', () => {
  const payload = normalizeCanonicalOpportunityList({
    schema_version: 'qx.opportunity-list.v1',
    pipeline_version: 'core_v1',
    source_mode: 'LIVE',
    items: [{evaluation_id: 'qxev1_00000000000070008000000000000001', source_mode: 'LIVE', lifecycle_state: 'ARMED'}],
    next_cursor: 'next-page',
    has_more: true,
  });
  assert.equal(payload.items[0].source_mode, 'LIVE');
  assert.equal(payload.next_cursor, 'next-page');
  assert.equal(payload.has_more, true);
});

test('non-LIVE envelopes and conflicting item modes cannot enter the list', () => {
  assert.throws(
    () => normalizeCanonicalOpportunityList({source_mode: 'REPLAY', items: []}),
    /response is not LIVE/,
  );
  const payload = normalizeCanonicalOpportunityList({
    source_mode: 'LIVE',
    items: [
      {evaluation_id: 'live', source_mode: 'LIVE'},
      {evaluation_id: 'replay', source_mode: 'REPLAY'},
    ],
  });
  assert.deepEqual(payload.items.map(item => item.evaluation_id), ['live']);
});

test('detail lookup preserves exact evaluation identity without POST', async () => {
  let request;
  const evaluationId = 'qxev1_00000000000070008000000000000001';
  const result = await fetchCanonicalOpportunityDetail(evaluationId, {
    expectedSymbol: 'SPY',
    expectedTimeframe: '5m',
    expectedEvaluationTimestamp: '2026-09-16T14:30:00+00:00',
    fetchImpl: async (url, options) => {
      request = {url, options};
      return {
        ok: true,
        json: async () => ({
          evaluation_id: evaluationId,
          source_mode: 'LIVE',
          symbol: 'SPY',
          timeframe: '5m',
          evaluation_timestamp: '2026-09-16T14:30:00Z',
          publication_state: 'RESEARCH_ONLY',
          lifecycle_state: 'ARMED',
          pipeline_version: 'core_v1',
          config_version: 'research_v1',
          engine_versions: {},
          decision: {symbol: 'SPY', timeframe: '5m'},
        }),
      };
    },
  });
  assert.equal(request.url, `/api/v2/qx/opportunities/${evaluationId}`);
  assert.equal(request.options.method, undefined);
  assert.equal(result.evaluation_id, evaluationId);
  assert.equal(result.current_lifecycle_state, 'ARMED');
});

test('detail lookup rejects symbol timeframe and timestamp identity mismatches', async () => {
  const evaluationId = 'qxev1_00000000000070008000000000000001';
  await assert.rejects(() => fetchCanonicalOpportunityDetail(evaluationId, {
    expectedSymbol: 'QQQ',
    expectedTimeframe: '15m',
    expectedEvaluationTimestamp: '2026-09-16T14:35:00Z',
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        evaluation_id: evaluationId,
        source_mode: 'LIVE',
        symbol: 'SPY',
        timeframe: '5m',
        evaluation_timestamp: '2026-09-16T14:30:00Z',
        pipeline_version: 'core_v1',
        decision: {},
      }),
    }),
  }), /symbol, timeframe, evaluation_timestamp/);
});
