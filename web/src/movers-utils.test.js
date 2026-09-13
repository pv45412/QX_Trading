import test from 'node:test';
import assert from 'node:assert/strict';
import {groupMovers} from './movers-utils.js';
test('movers separate absolute direction from benchmark outperformance and exclude invalid dates',()=>{
 const rows=[['A',.02,-.01],['B',-.01,.02],['C',0,0],['D',NaN,0]].map(([etf,return_1d,excess_1d])=>({etf,return_1d,excess_1d,as_of:'today'}));
 rows.push({etf:'OLD',return_1d:1,excess_1d:1,as_of:'yesterday'});
 const result=groupMovers(rows,'today');
 assert.deepEqual(result.gainers.map(r=>r.etf),['A']);
 assert.deepEqual(result.losers.map(r=>r.etf),['B']);
 assert.equal(result.unchanged,1);assert.equal(result.excluded,2);
 assert.equal(groupMovers(rows,null).covered,0);
});
