import test from 'node:test';
import assert from 'node:assert/strict';

import {fetchQxV2Evaluation} from './qx-v2-client.js';

test('client posts to the encoded canonical symbol endpoint', async () => {
  const calls = [];
  const result = await fetchQxV2Evaluation('BRK/B', {
    fetchImpl: async (...args) => {
      calls.push(args);
      return {ok: true, json: async () => ({pipeline_version: 'core_v1'})};
    },
  });

  assert.equal(calls[0][0], '/api/v2/qx/evaluate/BRK%2FB');
  assert.equal(calls[0][1].method, 'POST');
  assert.equal(result.pipeline_version, 'core_v1');
});

test('client propagates abort and unavailable responses', async () => {
  const controller = new AbortController();
  const aborted = fetchQxV2Evaluation('SPY', {
    signal: controller.signal,
    fetchImpl: async (_url, {signal}) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }),
  });
  controller.abort();
  await assert.rejects(aborted, error => error.name === 'AbortError');
  await assert.rejects(
    fetchQxV2Evaluation('SPY', {
      fetchImpl: async () => ({ok: false}),
    }),
    /unavailable/,
  );
});

test('client preserves canonical timeframe and evaluation timestamp query parameters', async () => {
  const calls = [];
  await fetchQxV2Evaluation('SPY', {
    timeframe: '15m',
    evaluationTimestamp: '2026-09-16T14:30:00Z',
    fetchImpl: async (...args) => {
      calls.push(args);
      return {ok: true, json: async () => ({pipeline_version: 'core_v1'})};
    },
  });
  const url = new URL(calls[0][0], 'http://127.0.0.1:5174');
  assert.equal(url.pathname, '/api/v2/qx/evaluate/SPY');
  assert.equal(url.searchParams.get('timeframe'), '15m');
  assert.equal(url.searchParams.get('evaluation_timestamp'), '2026-09-16T14:30:00Z');
});
