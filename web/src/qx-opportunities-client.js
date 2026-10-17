export async function fetchLegacyOpportunityDiscovery({signal, fetchImpl = fetch} = {}) {
  const response = await fetchImpl('/api/schwab/movers', {
    method: 'POST',
    headers: {'x-qx-refresh': '1'},
    signal,
  });
  if (!response.ok) throw new Error(`Live Schwab discovery unavailable (${response.status}).`);
  return response.json();
}

export async function evaluateCanonicalOpportunity(symbol, timeframe, {
  signal,
  fetchImpl = fetch,
} = {}) {
  const query = new URLSearchParams({timeframe});
  const response = await fetchImpl(
    `/api/v2/qx/evaluate/${encodeURIComponent(symbol)}?${query}`,
    {method: 'POST', signal},
  );
  if (!response.ok) throw new Error(`Canonical evaluation unavailable for ${symbol} (${response.status}).`);
  return response.json();
}

export async function scanCanonicalOpportunities({
  symbols,
  timeframe,
  limit = 8,
  signal,
  onProgress,
  fetchImpl = fetch,
} = {}) {
  const boundedLimit = Math.max(1, Math.min(10, Number(limit) || 8));
  const selected = [...new Set((symbols || []).map(value => String(value).trim().toUpperCase()).filter(Boolean))]
    .slice(0, boundedLimit);
  const results = [];
  for (const symbol of selected) {
    try {
      const evaluation = await evaluateCanonicalOpportunity(symbol, timeframe, {signal, fetchImpl});
      results.push({symbol, evaluation, error: null});
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      results.push({symbol, evaluation: null, error: error.message});
    }
    onProgress?.({completed: results.length, total: selected.length, symbol});
  }
  return results;
}

export async function fetchCanonicalOpportunities({
  signal,
  timeframe,
  symbols,
  states,
  publicationStates,
  direction,
  playbookId,
  horizonContext,
  limit = 100,
  queryAsOf,
  evaluatedAfter,
  evaluatedBefore,
  knowledgeAsOf,
  includeTerminal,
  includeBlocked,
  freshOnly,
  cursor,
  fetchImpl = fetch,
} = {}) {
  const query = new URLSearchParams({limit: String(limit)});
  appendValues(query, 'symbols', symbols);
  if (timeframe) query.set('timeframe', timeframe);
  appendValues(query, 'states', states);
  appendValues(query, 'publication_states', publicationStates);
  if (direction) query.set('direction', direction);
  if (playbookId) query.set('playbook_id', playbookId);
  if (horizonContext) query.set('horizon_context', horizonContext);
  if (queryAsOf) query.set('query_as_of', queryAsOf);
  if (evaluatedAfter) query.set('evaluated_after', evaluatedAfter);
  if (evaluatedBefore) query.set('evaluated_before', evaluatedBefore);
  if (knowledgeAsOf) query.set('knowledge_as_of', knowledgeAsOf);
  setBoolean(query, 'include_terminal', includeTerminal);
  setBoolean(query, 'include_blocked', includeBlocked);
  setBoolean(query, 'fresh_only', freshOnly);
  if (cursor) query.set('cursor', cursor);
  const response = await fetchImpl(`/api/v2/qx/opportunities?${query}`, {signal});
  if (!response.ok) throw new Error(`Canonical opportunities unavailable (${response.status}).`);
  return normalizeCanonicalOpportunityList(await response.json());
}

export function normalizeCanonicalOpportunityList(payload) {
  if (!payload || payload.source_mode !== 'LIVE') {
    throw new Error('Canonical opportunities unavailable: response is not LIVE.');
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  return {
    ...payload,
    items: items.filter(item => item?.source_mode === 'LIVE'),
  };
}

export async function fetchCanonicalOpportunityDetail(evaluationId, {
  signal,
  expectedSymbol,
  expectedTimeframe,
  expectedEvaluationTimestamp,
  fetchImpl = fetch,
} = {}) {
  const response = await fetchImpl(
    `/api/v2/qx/opportunities/${encodeURIComponent(evaluationId)}`,
    {signal},
  );
  if (!response.ok) throw new Error(`Canonical opportunity unavailable (${response.status}).`);
  const payload = await response.json();
  validateCanonicalOpportunityIdentity(payload, {
    evaluationId,
    symbol: expectedSymbol,
    timeframe: expectedTimeframe,
    evaluationTimestamp: expectedEvaluationTimestamp,
  });
  return {
    ...payload.decision,
    evaluation_id: payload.evaluation_id,
    evaluation_timestamp: payload.evaluation_timestamp,
    request_started_at: payload.request_started_at,
    publication_state: payload.publication_state,
    current_lifecycle_state: payload.lifecycle_state,
    pipeline_version: payload.pipeline_version,
    config_version: payload.config_version,
    engine_versions: payload.engine_versions,
  };
}

export function validateCanonicalOpportunityIdentity(payload, expected = {}) {
  const mismatches = [];
  if (payload?.source_mode !== 'LIVE') mismatches.push('source_mode');
  if (payload?.pipeline_version !== 'core_v1') mismatches.push('pipeline_version');
  if (expected.evaluationId && payload?.evaluation_id !== expected.evaluationId) mismatches.push('evaluation_id');
  if (expected.symbol && text(payload?.symbol).toUpperCase() !== text(expected.symbol).toUpperCase()) mismatches.push('symbol');
  if (expected.timeframe && text(payload?.timeframe).toLowerCase() !== text(expected.timeframe).toLowerCase()) mismatches.push('timeframe');
  if (expected.evaluationTimestamp && !sameTimestamp(payload?.evaluation_timestamp, expected.evaluationTimestamp)) mismatches.push('evaluation_timestamp');
  if (mismatches.length) throw new Error(`Canonical evaluation identity mismatch: ${mismatches.join(', ')}.`);
}

function sameTimestamp(left, right) {
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  return Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime === rightTime;
}

function text(value) {
  return typeof value === 'string' ? value : '';
}

function appendValues(query, name, values) {
  for (const value of Array.isArray(values) ? values : values ? [values] : []) {
    if (value != null && String(value)) query.append(name, String(value));
  }
}

function setBoolean(query, name, value) {
  if (typeof value === 'boolean') query.set(name, String(value));
}
