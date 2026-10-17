import test from 'node:test';
import assert from 'node:assert/strict';

import {createPortfolioFixture} from './qx-portfolio-fixtures.js';
import {buildPortfolioWorkspaceView} from './qx-portfolio-model.js';

test('Portfolio model preserves canonical account and position fields', () => {
  const fixture = createPortfolioFixture('healthy');
  const view = buildPortfolioWorkspaceView(fixture.snapshot);
  assert.equal(view.snapshot.accountId, 'qxacct_fixture_safe_1');
  assert.equal(view.snapshot.positions[0].symbol, 'AAPL');
  assert.equal(view.snapshot.positions[0].marketValue, 19000);
  assert.equal(view.snapshot.positions[0].sectorId, 'XLK');
  assert.equal(view.snapshot.status, 'COMPLETE');
});

test('Portfolio model never converts missing values to zero', () => {
  const fixture = createPortfolioFixture('partial');
  fixture.snapshot.positions[0].unrealized_pnl = null;
  fixture.snapshot.positions[0].delta = null;
  const view = buildPortfolioWorkspaceView(fixture.snapshot);
  assert.equal(view.snapshot.dailyUnrealizedPnl, null);
  assert.equal(view.snapshot.totalUnrealizedPnl, null);
  assert.equal(view.snapshot.positions[0].unrealizedPnl, null);
  assert.equal(view.snapshot.positions[0].delta, null);
});

test('Portfolio model projects Phase 10 output without recalculation', () => {
  const fixture = createPortfolioFixture('vetoed');
  const view = buildPortfolioWorkspaceView(fixture.snapshot, fixture.evaluation);
  assert.equal(view.candidateImpact.state, 'PORTFOLIO_VETOED');
  assert.equal(view.candidateImpact.bindingConstraint, 'SECTOR_CONCENTRATION');
  assert.equal(view.candidateImpact.symbolExposureBefore, 19500);
  assert.equal(view.candidateImpact.symbolExposureAfter, 19980);
  assert.deepEqual(view.candidateImpact.reasonCodes, fixture.evaluation.portfolio_risk.reason_codes);
});

test('partial, stale, sector, Greek, and no-account states remain distinct', () => {
  const states = Object.fromEntries(['partial','stale','sector_unknown','greeks_unavailable','no_account'].map(state => {
    const fixture = createPortfolioFixture(state);
    return [state, buildPortfolioWorkspaceView(fixture.snapshot).snapshot.status];
  }));
  assert.deepEqual(states, {
    partial: 'PARTIAL', stale: 'STALE', sector_unknown: 'PARTIAL',
    greeks_unavailable: 'PARTIAL', no_account: 'UNAVAILABLE',
  });
});

test('unknown sector never becomes an approval bucket', () => {
  const fixture = createPortfolioFixture('sector_unknown');
  const view = buildPortfolioWorkspaceView(fixture.snapshot);
  assert.equal(view.snapshot.positions[1].sectorStatus, 'UNKNOWN');
  assert.equal(view.snapshot.positions[1].sectorId, null);
  assert.equal(JSON.stringify(view).includes('Unassigned'), false);
});
