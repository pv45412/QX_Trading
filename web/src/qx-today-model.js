import {adaptQxV2Evaluation} from './qx-v2-adapter.js';

const activeStates = new Set(['WATCH', 'ARMED', 'TRIGGERED', 'TRADEABLE', 'OPTIONS_SUITABLE']);
const attentionOrder = new Map([
  ['TRIGGERED', 0],
  ['TRADEABLE', 1],
  ['OPTIONS_SUITABLE', 2],
  ['ARMED', 3],
  ['WATCH', 4],
]);

export function marketPulseFromEvaluations(evaluations = {}, quotes = {}) {
  return ['SPX', 'SPY', 'QQQ'].map(symbol => {
    const entry = evaluations[symbol];
    const quoteEntry = quotes[symbol];
    const canonical = adaptQxV2Evaluation(entry?.data);
    const quote = quoteEntry?.data && typeof quoteEntry.data === 'object' ? quoteEntry.data : null;
    const bars = canonical?.dependencies.find(dependency => dependency.name === 'bars') || null;
    const quoteStatus = textOrNull(quote?.status);
    const quoteHasValue = [quote?.last, quote?.bid, quote?.ask].some(value => finiteOrNull(value) != null);
    const quoteAvailable = quoteHasValue && quoteStatus !== 'UNAVAILABLE';
    const barsAvailable = bars?.available === true;
    const canonicalBlocked = canonical?.publicationState === 'BLOCKED';
    return {
      symbol,
      status: canonicalBlocked
        ? 'BLOCKED'
        : canonical && quoteAvailable && barsAvailable
          ? 'AVAILABLE'
          : quoteAvailable || barsAvailable
            ? 'PARTIAL'
            : 'UNAVAILABLE',
      direction: canonical?.directionLabel ?? null,
      regime: canonical?.marketRegime.trend ?? null,
      volatility: canonical?.marketRegime.volatility ?? null,
      session: canonical?.marketRegime.session ?? null,
      evaluationTimestamp: canonical?.evaluationTimestamp ?? null,
      publicationState: canonical?.publicationState ?? null,
      pipelineVersion: canonical?.pipelineVersion ?? null,
      quoteLast: finiteOrNull(quote?.last),
      quoteBid: finiteOrNull(quote?.bid),
      quoteAsk: finiteOrNull(quote?.ask),
      quoteChangePct: finiteOrNull(quote?.change_pct),
      quoteVolume: finiteOrNull(quote?.volume),
      quoteSource: textOrNull(quote?.source),
      quoteAssetType: textOrNull(quote?.asset_type),
      quoteFieldEvidence: objectOrNull(quote?.field_evidence),
      quoteRealtime: typeof quote?.realtime === 'boolean' ? quote.realtime : null,
      quoteTimestamp: textOrNull(quote?.quote_timestamp),
      quoteFreshness: textOrNull(quote?.freshness),
      quoteStatus,
      barSource: textOrNull(bars?.source),
      barDataAsOf: textOrNull(bars?.dataAsOf),
      barFreshness: textOrNull(bars?.freshness),
      reason: canonical?.reasons[0]
        ?? entry?.error
        ?? quoteEntry?.error
        ?? (!canonical ? (symbol === 'SPX' ? 'Canonical SPX context is not available.' : 'Canonical evaluation unavailable.') : null),
    };
  });
}

export function activeTodayOpportunities(rows, limit = 5) {
  return rows.filter(row => activeStates.has(row.state))
    .sort((left, right) => (attentionOrder.get(left.state) ?? 99) - (attentionOrder.get(right.state) ?? 99)
      || left.symbol.localeCompare(right.symbol))
    .slice(0, limit);
}

export function portfolioAttentionFromSnapshot(snapshot, error = '') {
  if (error) return {status: 'UNAVAILABLE', detail: error};
  if (!snapshot || snapshot.status === 'UNAVAILABLE') {
    return {
      status: 'UNAVAILABLE',
      detail: Array.isArray(snapshot?.reason_codes) && snapshot.reason_codes.length
        ? readable(snapshot.reason_codes[0])
        : 'Canonical account snapshot is unavailable.',
    };
  }
  const reasons = Array.isArray(snapshot.reason_codes) ? snapshot.reason_codes : [];
  const positions = Array.isArray(snapshot.positions) ? snapshot.positions.length : 0;
  if (snapshot.freshness && snapshot.freshness !== 'FRESH') {
    return {
      status: 'STALE',
      detail: `Canonical account evidence is ${readable(snapshot.freshness)}. Review Portfolio before relying on position context.`,
    };
  }
  if (reasons.length || snapshot.status === 'PARTIAL') {
    return {
      status: 'PARTIAL',
      detail: `${positions} position${positions === 1 ? '' : 's'} loaded; ${reasons.length ? readable(reasons[0]) : 'account evidence is partial'}.`,
    };
  }
  return {
    status: 'AVAILABLE',
    detail: `No canonical portfolio exceptions reported across ${positions} position${positions === 1 ? '' : 's'}.`,
  };
}

export function materialHealthItems({evaluations = {}, operations = null, fixtureItems = []} = {}) {
  const items = [...fixtureItems];
  for (const symbol of ['SPY', 'QQQ', 'SPX']) {
    const entry = evaluations[symbol];
    if (entry?.error) items.push({code: 'CANONICAL_MARKET_CONTEXT_UNAVAILABLE', label: `${symbol} canonical context unavailable`, detail: entry.error, destination: 'system'});
    else if (entry?.data?.publication_state === 'BLOCKED') items.push({
      code: 'CANONICAL_PIPELINE_BLOCKED',
      label: `${symbol} canonical pipeline blocked`,
      detail: firstReason(entry.data.reason_codes),
      destination: 'system',
    });
  }
  if (operations && operations.status !== 'OK') items.push({
    code: 'SYSTEM_HEALTH_DEGRADED',
    label: 'Decision infrastructure degraded',
    detail: String(operations.status),
    destination: 'system',
  });
  for (const component of operations?.components || []) {
    if (component.status !== 'OK') items.push({
      code: 'SYSTEM_COMPONENT_DEGRADED',
      label: `${component.name || 'System component'} ${component.status || 'UNAVAILABLE'}`,
      detail: component.details || 'Material health exception reported.',
      destination: 'system',
    });
  }
  return dedupe(items);
}

function firstReason(reasons) {
  return Array.isArray(reasons) && reasons.length ? reasons[0] : 'No canonical reason supplied.';
}

function readable(value) {
  return String(value).replaceAll('_', ' ').toLowerCase();
}

function finiteOrNull(value) {
  if (value == null || typeof value === 'boolean' || (typeof value === 'string' && value.trim() === '')) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function objectOrNull(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
}

function textOrNull(value) {
  return value == null || String(value).trim() === '' ? null : String(value);
}

function dedupe(items) {
  const seen = new Set();
  return items.filter(item => {
    const key = `${item.code}:${item.label}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
