import {test} from 'node:test';
import assert from 'node:assert/strict';
import {csvCell, rankingCsv, formatTimestampET} from './data-utils.js';

test('CSV escapes commas, quotes and line breaks', () => {
  assert.equal(csvCell('A, "B"\nC'), '"A, ""B""\nC"');
});
test('missing data stays empty and negative numeric values stay numeric', () => {
  assert.equal(csvCell(null), '');
  assert.equal(csvCell(-.25), '"-0.25"');
});
test('untrusted strings cannot become spreadsheet formulas', () => {
  assert.equal(csvCell('=1+1'), '"\'=1+1"');
  assert.equal(csvCell(' @SUM(A1)'), '"\' @SUM(A1)"');
});
test('exports fractional units with original field names', () => {
  const csv = rankingCsv([{etf:'XLK',sector:'Technology',relative_20d:.12}]);
  assert.equal(csv.split('\r\n')[1], '"XLK","Technology",,"0.12",');
});

test('timestamps show Eastern time across DST and UTC date boundaries', () => {
  assert.equal(formatTimestampET('2026-09-11T00:30:00Z'), 'Sep 10, 2026, 08:30 PM EDT');
  assert.equal(formatTimestampET('2026-01-11T12:30:00+00:00'), 'Jan 11, 2026, 07:30 AM EST');
  assert.equal(formatTimestampET('2026-11-01T05:30:00Z'), 'Nov 01, 2026, 01:30 AM EDT');
  assert.equal(formatTimestampET('2026-11-01T06:30:00Z'), 'Nov 01, 2026, 01:30 AM EST');
});

test('legacy naive timestamps use UTC while daily session labels never shift', () => {
  assert.equal(formatTimestampET('2026-09-11 00:30:00.123456'), 'Sep 10, 2026, 08:30 PM EDT');
  assert.equal(formatTimestampET('2026-09-11'), '2026-09-11');
  assert.equal(formatTimestampET('2026-09-10T20:30:00-04:00'), formatTimestampET('2026-09-11T00:30:00Z'));
});

test('invalid timestamps remain unavailable instead of being normalized', () => {
  for (const value of [null, undefined, 0, '', 'today', '2026-02-30', '2026-02-30T12:00:00Z',
    '2026-09-11T24:00:00Z', '2026-09-11T12:60:00Z', '2026-09-11T12:00:60Z', '2026-09-11T12:00:00+99:00']) {
    assert.equal(formatTimestampET(value), 'Unavailable');
  }
});
