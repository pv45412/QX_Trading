export function summarizeHoldings(rows) {
  if (!Array.isArray(rows) || !rows.length) return null;
  const seen = new Set();
  for (const row of rows) {
    if (!row || typeof row.symbol !== 'string' || !row.symbol.trim() ||
        seen.has(row.symbol.trim().toUpperCase()) || typeof row.weight !== 'number' ||
        !Number.isFinite(row.weight) || row.weight < 0 || row.weight > 1) return null;
    seen.add(row.symbol.trim().toUpperCase());
  }
  const ranked = [...rows].sort((a, b) => b.weight - a.weight);
  const total = ranked.reduce((sum, row) => sum + row.weight, 0);
  // Allow small rounding error from published constituent percentages.
  if (total > 1.001) return null;
  return {ranked, total, topThree: ranked.length >= 3
    ? ranked.slice(0, 3).reduce((sum, row) => sum + row.weight, 0) : null};
}

export function strengthOrder(rows) {
  return [...rows].sort((a,b)=>{
    const x=a.analytics?.rs_change, y=b.analytics?.rs_change;
    if (!Number.isFinite(x)) return Number.isFinite(y) ? 1 : a.symbol.localeCompare(b.symbol);
    if (!Number.isFinite(y)) return -1;
    return y-x || a.symbol.localeCompare(b.symbol);
  });
}
