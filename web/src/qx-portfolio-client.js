export async function fetchQxPortfolio({
  signal,
  evaluationTimestamp,
  fetchImpl = globalThis.fetch,
} = {}) {
  const query = new URLSearchParams();
  if (evaluationTimestamp) query.set('evaluation_timestamp', evaluationTimestamp);
  const response = await fetchImpl(`/api/v2/qx/portfolio${query.size ? `?${query}` : ''}`, {signal});
  if (!response.ok) throw new Error('Canonical Portfolio snapshot is unavailable.');
  return response.json();
}
