export async function fetchResearchSnapshot(symbol, {signal, fetchImpl = globalThis.fetch} = {}) {
  const response = await fetchImpl(`/api/market/${encodeURIComponent(symbol)}/snapshot`, {signal});
  if (!response.ok) throw new Error('Source-backed symbol research is unavailable.');
  return response.json();
}

export async function runResearchBacktest(symbol, {signal, fetchImpl = globalThis.fetch} = {}) {
  const response = await fetchImpl('/api/backtest/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({symbol}),
    signal,
  });
  if (!response.ok) throw new Error('Historical backtest data is unavailable for this symbol.');
  return response.json();
}

