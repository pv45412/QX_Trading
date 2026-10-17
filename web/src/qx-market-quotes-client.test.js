import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchMarketQuote} from './qx-market-quotes-client.js';

test('market quote client requests the canonical same-origin endpoint', async () => {
  const calls = [];
  const payload = {
    symbol: 'SPX', resolved_symbol: '$SPX', source: 'schwab', status: 'AVAILABLE',
    last: 6618.21, bid: 6617.9, ask: 6618.4, change_pct: -0.0042, volume: 1234,
    quote_timestamp: '2026-09-17T15:59:58Z', trade_timestamp: '2026-09-17T15:59:57Z',
    realtime: true, retrieved_at: '2026-09-17T16:00:00Z', age_seconds: 2,
    freshness: 'FRESH',
  };
  const result = await fetchMarketQuote(' spx ', {
    signal: 'quote-signal',
    fetchImpl: async (path, options) => {
      calls.push({path, options});
      return {ok: true, json: async () => payload};
    },
  });

  assert.deepEqual(calls, [{
    path: '/api/v2/market/quote/SPX',
    options: {method: 'GET', signal: 'quote-signal'},
  }]);
  assert.deepEqual(result, payload);
  assert.equal(result.resolved_symbol, '$SPX');
  assert.equal(result.source, 'schwab');
  assert.equal(result.realtime, true);
});

test('market quote client fails closed on an unsuccessful response', async () => {
  await assert.rejects(
    fetchMarketQuote('QQQ', {fetchImpl: async () => ({ok: false})}),
    /QQQ quote is unavailable/,
  );
});
