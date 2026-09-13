import {test} from 'node:test';
import assert from 'node:assert/strict';
import {summarizeHoldings, strengthOrder} from './holdings-utils.js';

test('ranks without mutation and summarizes only reported holdings', () => {
  const rows = [{symbol:'B',weight:.1},{symbol:'A',weight:.3},{symbol:'C',weight:.2},{symbol:'D',weight:.05}];
  const result = summarizeHoldings(rows);
  assert.equal(result.ranked[0].symbol, 'A');
  assert.equal(rows[0].symbol, 'B');
  assert.ok(Math.abs(result.total - .65) < 1e-10);
  assert.ok(Math.abs(result.topThree - .6) < 1e-10);
});
test('incomplete coverage does not invent a top-three total', () => {
  assert.equal(summarizeHoldings([{symbol:'A',weight:.2}]).topThree, null);
});
test('strength sorting puts missing metrics last without changing portfolio order', () => {
  const rows=[{symbol:'Z'}, {symbol:'B',analytics:{rs_change:-.1}}, {symbol:'A',analytics:{rs_change:.2}}];
  assert.deepEqual(strengthOrder(rows).map(r=>r.symbol), ['A','B','Z']);
  assert.equal(rows[0].symbol,'Z');
});
test('rejects missing, duplicate, nonfinite and impossible weights', () => {
  for (const rows of [null, [], [null], [{symbol:'A',weight:NaN}],
    [{symbol:'A',weight:-.2}], [{symbol:'A',weight:'0.2'}],
    [{symbol:'A',weight:.8},{symbol:'B',weight:.8}],
    [{symbol:'A',weight:.1},{symbol:' a ',weight:.2}]]) {
    assert.equal(summarizeHoldings(rows), null);
  }
});
