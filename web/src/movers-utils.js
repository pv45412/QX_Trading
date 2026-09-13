export function groupMovers(rows, asOf) {
 const valid = rows.filter(r => asOf && r.as_of === asOf && Number.isFinite(r.return_1d) && Number.isFinite(r.excess_1d));
 const order = (a,b) => b.return_1d-a.return_1d || a.etf.localeCompare(b.etf);
 return {
  gainers: valid.filter(r=>r.return_1d>0).sort(order),
  losers: valid.filter(r=>r.return_1d<0).sort((a,b)=>a.return_1d-b.return_1d || a.etf.localeCompare(b.etf)),
  unchanged: valid.filter(r=>r.return_1d===0).length,
  covered: valid.length, excluded: rows.length-valid.length,
 };
}
