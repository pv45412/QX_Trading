export async function fetchMarketQuote(symbol, {
  signal,
  fetchImpl = globalThis.fetch,
} = {}) {
  const canonicalSymbol = String(symbol || '').trim().toUpperCase();
  const response = await fetchImpl(
    `/api/v2/market/quote/${encodeURIComponent(canonicalSymbol)}`,
    {method: 'GET', signal},
  );
  if (!response.ok) throw new Error(`${canonicalSymbol || 'Market'} quote is unavailable.`);
  return response.json();
}
