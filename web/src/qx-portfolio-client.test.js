import test from 'node:test';
import assert from 'node:assert/strict';

import {fetchQxPortfolio} from './qx-portfolio-client.js';

test('Portfolio client requests the canonical read-only endpoint', async () => {
  const calls = [];
  const result = await fetchQxPortfolio({
    evaluationTimestamp: '2026-09-16T14:35:00Z',
    fetchImpl: async (url, options) => {
      calls.push([url, options]);
      return {ok: true, json: async () => ({status: 'COMPLETE'})};
    },
  });
  assert.equal(result.status, 'COMPLETE');
  assert.equal(calls.length, 1);
  assert.match(calls[0][0], /^\/api\/v2\/qx\/portfolio\?evaluation_timestamp=/);
  assert.equal(calls[0][1].method, undefined);
});

test('Portfolio client does not send credentials or account identifiers', async () => {
  let requestedUrl = '';
  await fetchQxPortfolio({fetchImpl: async url => {
    requestedUrl = url;
    return {ok: true, json: async () => ({})};
  }});
  assert.equal(requestedUrl, '/api/v2/qx/portfolio');
  assert.doesNotMatch(requestedUrl, /account|token|secret/i);
});
