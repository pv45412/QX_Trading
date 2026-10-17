import test from 'node:test';
import assert from 'node:assert/strict';
import {buildBacktestView, buildResearchSnapshot, researchModeForRoute} from './qx-research-model.js';

test('legacy research routes map to one deterministic Research mode', () => {
  assert.equal(researchModeForRoute('ticker_history'), 'symbol');
  assert.equal(researchModeForRoute('relative_strength'), 'relative_strength');
  assert.equal(researchModeForRoute('options_ideas'), 'options_strategy');
  assert.equal(researchModeForRoute('backtest'), 'historical');
  assert.equal(researchModeForRoute('research', 'long_term'), 'long_term');
});

test('research snapshot preserves source-backed values without lifecycle inference', () => {
  const view = buildResearchSnapshot({
    symbol: 'NVDA', status: 'LIVE', source_class: 'SOURCE_BACKED', source: 'schwab',
    last_price: 181.25, data_as_of: '2026-09-16T20:00:00Z',
    structure: {current_trend: 'BEARISH', structure_score: 0, latest_bos: 'BEARISH_BOS', latest_choch: null, active_fvgs: []},
  }, 'NVDA');
  assert.equal(view.lastPrice, 181.25);
  assert.equal(view.structureScore, 0);
  assert.equal(view.latestChoch, null);
  assert.equal(Object.hasOwn(view, 'lifecycleState'), false);
});

test('unavailable source cannot expose fallback price or structure', () => {
  const view = buildResearchSnapshot({symbol: 'MISSING', status: 'UNAVAILABLE', source_class: 'UNAVAILABLE', last_price: 187.5,
    structure: {current_trend: 'BULLISH'}}, 'MISSING');
  assert.equal(view.lastPrice, null);
  assert.equal(view.trend, null);
  assert.equal(view.status, 'UNAVAILABLE');
});

test('backtest results remain historical metrics and preserve zero values', () => {
  const view = buildBacktestView({symbol: 'SPY', total_trades: 0, win_rate: 0, average_return_pct: 0, trades: []});
  assert.deepEqual(view, {symbol: 'SPY', totalTrades: 0, winRate: 0, averageReturnPct: 0, trades: []});
  assert.equal(Object.hasOwn(view, 'confidence'), false);
});

