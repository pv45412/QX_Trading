export async function fetchQxV2Evaluation(symbol, {
  signal,
  timeframe,
  evaluationTimestamp,
  fetchImpl = globalThis.fetch,
} = {}) {
  const query = new URLSearchParams();
  if (timeframe) query.set('timeframe', timeframe);
  if (evaluationTimestamp) query.set('evaluation_timestamp', evaluationTimestamp);
  const suffix = query.size ? `?${query}` : '';
  const response = await fetchImpl(
    `/api/v2/qx/evaluate/${encodeURIComponent(symbol)}${suffix}`,
    {method: 'POST', signal},
  );
  if (!response.ok) throw new Error('Canonical V2 evaluation is unavailable.');
  return response.json();
}
