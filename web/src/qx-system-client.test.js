import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchSystemJobStatus, fetchSystemOverview} from './qx-system-client.js';

test('System client uses same-origin read-only endpoints', async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (path, options) => {
    calls.push({path, options});
    return {ok: true, json: async () => ({status: 'OK'})};
  };
  try {
    await fetchSystemOverview();
    await fetchSystemJobStatus();
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(calls.map(call => call.path), ['/api/system/overview', '/api/system/jobs/status']);
  assert.equal(calls.every(call => !call.options.method || call.options.method === 'GET'), true);
});

