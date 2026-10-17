import test from 'node:test';
import assert from 'node:assert/strict';

import {createQxV2PreviewFixture, previewStates} from './qx-v2-fixtures.js';

test('preview fixtures cover every approved review state and remain clearly labeled', () => {
  assert.deepEqual(previewStates, [
    'NO_SETUP', 'WATCH', 'ARMED', 'TRIGGERED', 'TRADEABLE', 'OPTIONS_NOT_SUITABLE', 'BLOCKED',
    'PORTFOLIO_VETOED', 'PORTFOLIO_APPROVED',
  ]);
  for (const state of previewStates) {
    const fixture = createQxV2PreviewFixture(state, 'SPY');
    assert.equal(fixture.current_lifecycle_state, state);
    assert.equal(fixture.pipeline_version, 'core_v1');
    assert.match(fixture.evidence_summary[0], /Fixture payload/);
  }
});

test('options-not-suitable fixture preserves upstream tradeability evidence', () => {
  const fixture = createQxV2PreviewFixture('OPTIONS_NOT_SUITABLE', 'SPY');
  assert.equal(fixture.tradeability.state, 'TRADEABLE');
  assert.equal(fixture.options_expression.state, 'NOT_SUITABLE');
  assert.equal(fixture.portfolio_risk, undefined);
});

test('armed preview is explicitly untriggered and blocked preview is publication blocked', () => {
  const armed = createQxV2PreviewFixture('ARMED', 'SPY');
  const blocked = createQxV2PreviewFixture('BLOCKED', 'SPY');

  assert.equal(armed.trigger.state, 'ARMED');
  assert.equal(armed.trigger.trigger_event, null);
  assert.equal(blocked.trigger.publication_state, 'BLOCKED');
});

test('preview fixture symbol changes update canonical identity and evidence ids', () => {
  const spy = createQxV2PreviewFixture('TRIGGERED', 'SPY');
  const qqq = createQxV2PreviewFixture('TRIGGERED', 'QQQ');

  assert.equal(spy.symbol, 'SPY');
  assert.equal(qqq.symbol, 'QQQ');
  assert.notEqual(spy.trigger.trigger_event.trigger_event_id, qqq.trigger.trigger_event.trigger_event_id);
});

test('portfolio terminal fixtures use synchronized account evidence', () => {
  for (const state of ['PORTFOLIO_VETOED', 'PORTFOLIO_APPROVED']) {
    const fixture = createQxV2PreviewFixture(state, 'SPY');
    assert.equal(fixture.data_dependencies.account_snapshot.sync_status, 'SYNCED');
    assert.equal(fixture.portfolio_risk.evidence_ladder.account_snapshot, 'SYNCED');
  }
});
