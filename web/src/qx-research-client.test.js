import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchResearchSnapshot, runResearchBacktest} from './qx-research-client.js';

test('research client uses encoded same-origin read endpoint', async () => {
  const calls = [];
  const result = await fetchResearchSnapshot('BRK/B', {fetchImpl: async (url, options) => {
    calls.push([url, options]); return {ok: true, json: async () => ({symbol: 'BRK/B'})};
  }});
  assert.equal(calls[0][0], '/api/market/BRK%2FB/snapshot');
  assert.equal(calls[0][1].method, undefined);
  assert.equal(result.symbol, 'BRK/B');
});

test('backtest client submits only the selected symbol', async () => {
  const calls = [];
  await runResearchBacktest('NVDA', {fetchImpl: async (url, options) => {
    calls.push([url, options]); return {ok: true, json: async () => ({symbol: 'NVDA'})};
  }});
  assert.equal(calls[0][0], '/api/backtest/run');
  assert.equal(calls[0][1].method, 'POST');
  assert.deepEqual(JSON.parse(calls[0][1].body), {symbol: 'NVDA'});
});

