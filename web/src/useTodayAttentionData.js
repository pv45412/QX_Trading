import {useCallback, useEffect, useState} from 'react';
import {fetchCanonicalOpportunities, fetchLegacyOpportunityDiscovery} from './qx-opportunities-client';
import {fetchMarketQuote} from './qx-market-quotes-client';
import {fetchQxPortfolio} from './qx-portfolio-client';
import {fetchQxV2Evaluation} from './qx-v2-client';

export default function useTodayAttentionData({enabled, timeframe, horizon}) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState(initialState);

  useEffect(() => {
    if (!enabled) {
      setState(initialState);
      return undefined;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    let active = true;
    setState({...initialState, loading: true});
    Promise.allSettled([
      fetchQxV2Evaluation('SPY', {signal: controller.signal, timeframe}),
      fetchQxV2Evaluation('QQQ', {signal: controller.signal, timeframe}),
      fetchQxV2Evaluation('SPX', {signal: controller.signal, timeframe}),
      fetchMarketQuote('SPY', {signal: controller.signal}),
      fetchMarketQuote('QQQ', {signal: controller.signal}),
      fetchMarketQuote('SPX', {signal: controller.signal}),
      fetchJson('/api/ops/health', controller.signal),
      fetchLegacyOpportunityDiscovery({signal: controller.signal}),
      fetchCanonicalOpportunities({
        signal: controller.signal,
        timeframe,
        horizonContext: horizon,
        states: ['WATCH', 'ARMED', 'TRIGGERED', 'TRADEABLE', 'OPTIONS_SUITABLE'],
        includeTerminal: false,
        includeBlocked: false,
        freshOnly: true,
        limit: 5,
      }),
      fetchQxPortfolio({signal: controller.signal}),
    ]).then(([spy, qqq, spx, spyQuote, qqqQuote, spxQuote, operations, legacy, canonical, portfolio]) => {
      if (!active) return;
      setState({
        loading: false,
        evaluations: {
          SPY: settledEvaluation(spy),
          QQQ: settledEvaluation(qqq),
          SPX: settledEvaluation(spx),
        },
        quotes: {
          SPY: settledQuote(spyQuote),
          QQQ: settledQuote(qqqQuote),
          SPX: settledQuote(spxQuote),
        },
        operations: operations.status === 'fulfilled' ? operations.value : null,
        operationsError: settledError(operations),
        legacyPayload: legacy.status === 'fulfilled' ? legacy.value : null,
        legacyError: settledError(legacy),
        canonicalPayload: canonical.status === 'fulfilled' ? canonical.value : null,
        canonicalError: settledError(canonical),
        portfolioPayload: portfolio.status === 'fulfilled' ? portfolio.value : null,
        portfolioError: settledError(portfolio),
      });
    }).finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [enabled, horizon, revision, timeframe]);

  const retry = useCallback(() => setRevision(value => value + 1), []);
  return {...state, retry};
}

const initialState = {
  loading: false,
  evaluations: {},
  quotes: {},
  operations: null,
  operationsError: '',
  legacyPayload: null,
  legacyError: '',
  canonicalPayload: null,
  canonicalError: '',
  portfolioPayload: null,
  portfolioError: '',
};

async function fetchJson(path, signal) {
  const response = await fetch(path, {signal});
  if (!response.ok) throw new Error(`Request unavailable (${response.status}).`);
  return response.json();
}

function settledEvaluation(result) {
  return result.status === 'fulfilled'
    ? {data: result.value, error: ''}
    : {data: null, error: settledError(result)};
}

function settledQuote(result) {
  return result.status === 'fulfilled'
    ? {data: result.value, error: ''}
    : {data: null, error: settledError(result)};
}

function settledError(result) {
  if (result.status === 'fulfilled') return '';
  return result.reason?.name === 'AbortError' ? 'Request timed out.' : result.reason?.message || 'Request unavailable.';
}
