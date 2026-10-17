import test from 'node:test';
import assert from 'node:assert/strict';
import {createQxV2PreviewFixture} from './qx-v2-fixtures.js';
import {buildTradeWorkspaceView} from './qx-trade-workspace-model.js';

test('armed summary never infers trigger confirmation from trigger object presence', () => {
  const result = buildTradeWorkspaceView(createQxV2PreviewFixture('ARMED'));
  assert.equal(result.canonical.triggerSource, 'UNCONFIRMED');
  assert.match(result.waitingFor, /Wait for the canonical trigger/);
  assert.match(result.isThereATrade, /Not yet/);
});

test('triggered and not-suitable states preserve their distinct next gates', () => {
  const triggered = buildTradeWorkspaceView(createQxV2PreviewFixture('TRIGGERED'));
  const notSuitable = buildTradeWorkspaceView(createQxV2PreviewFixture('OPTIONS_NOT_SUITABLE'));
  assert.match(triggered.waitingFor, /Tradeability/);
  assert.equal(triggered.canonical.triggerSource, 'CONFIRMED');
  assert.equal(notSuitable.canonical.optionsSummary.state, 'NOT_SUITABLE');
  assert.match(notSuitable.isThereATrade, /No canonical options expression/);
});

test('portfolio approval remains explicitly separate from execution readiness', () => {
  const result = buildTradeWorkspaceView(createQxV2PreviewFixture('PORTFOLIO_APPROVED'));
  assert.match(result.isThereATrade, /Execution is not enabled/);
  assert.equal(result.canonical.portfolioSummary.approvedContractsCap, 2);
});

test('workspace model preserves zero values and unavailable downstream stages', () => {
  const fixture = createQxV2PreviewFixture('TRADEABLE');
  fixture.tradeability.participation_score = 0;
  fixture.tradeability.risk_reward_to_best_structural_target = 0;
  const result = buildTradeWorkspaceView(fixture);
  assert.equal(result.canonical.tradeabilitySummary.participationScore, 0);
  assert.equal(result.canonical.tradeabilitySummary.structuralRiskReward, 0);
  assert.equal(result.canonical.optionsSummary.state, null);
  assert.equal(result.canonical.portfolioSummary.state, null);
});

test('market driver remains unavailable and is not inferred from bullish context', () => {
  const result = buildTradeWorkspaceView(createQxV2PreviewFixture('PORTFOLIO_APPROVED'));
  assert.match(result.whatIsHappening, /^Market driver unavailable\./);
});
