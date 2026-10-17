import test from 'node:test';
import assert from 'node:assert/strict';
import {buildSystemJobStatus, buildSystemOverview, systemTabForRoute} from './qx-system-model.js';

test('legacy System routes map to one consolidated workspace tab', () => {
  assert.equal(systemTabForRoute('system_overview'), 'overview');
  assert.equal(systemTabForRoute('schwab'), 'providers');
  assert.equal(systemTabForRoute('data_cache'), 'data');
  assert.equal(systemTabForRoute('jobs'), 'jobs');
  assert.equal(systemTabForRoute('run_history'), 'runs');
  assert.equal(systemTabForRoute('strategy_rules'), 'rules');
});

test('System overview preserves zero values and explicit unavailable states', () => {
  const view = buildSystemOverview({status: 'DEGRADED', pipeline: {pipeline_version: 'core_v1', rules_config_version: null, status: 'UNAVAILABLE'},
    cache: {status: 'AVAILABLE', freshness_status: 'UNVERIFIED', total_files: 0, total_symbols: 0, total_size_mb: 0, periods: {}},
    run_history: {status: 'EMPTY', records: []}, components: []});
  assert.equal(view.cache.totalFiles, 0);
  assert.equal(view.cache.totalSizeMb, 0);
  assert.equal(view.rulesConfigVersion, null);
  assert.equal(view.runHistoryStatus, 'EMPTY');
});

test('System models never project unknown secret or token fields', () => {
  const payload = {client_secret: 'secret', access_token: 'token', pipeline: {}, cache: {}, run_history: {}, components: []};
  const overview = buildSystemOverview(payload);
  const job = buildSystemJobStatus({...payload, configured: true});
  assert.equal(JSON.stringify({overview, job}).includes('secret'), false);
  assert.equal(JSON.stringify({overview, job}).includes('token'), false);
});

