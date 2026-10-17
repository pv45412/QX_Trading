import {useCallback, useEffect, useState} from 'react';
import {fetchQxV2Evaluation} from './qx-v2-client';
import {fetchCanonicalOpportunityDetail} from './qx-opportunities-client';

export default function useQxV2Evaluation(symbol, enabled, {
  timeframe = '5m',
  evaluationTimestamp = null,
  evaluationId = null,
} = {}) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({data: null, error: '', loading: false});

  useEffect(() => {
    if (!enabled || !symbol) {
      setState({data: null, error: '', loading: false});
      return undefined;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let active = true;
    setState({data: null, error: '', loading: true});
    const started = performance.now();
    const request = evaluationId
      ? fetchCanonicalOpportunityDetail(evaluationId, {
        signal: controller.signal,
        expectedSymbol: symbol,
        expectedTimeframe: timeframe,
        expectedEvaluationTimestamp: evaluationTimestamp,
      })
      : fetchQxV2Evaluation(symbol, {
        signal: controller.signal,
        timeframe,
        evaluationTimestamp,
      });
    request
      .then(data => {
        if (active) setState({data, error: '', loading: false});
      })
      .catch(error => {
        if (active) {
          setState({
            data: null,
            loading: false,
            error: error.name === 'AbortError'
              ? 'Canonical V2 evaluation timed out.'
              : error.message,
          });
        }
      })
      .finally(() => {
        clearTimeout(timeout);
        if (!controller.signal.aborted) {
          const elapsedMs = performance.now() - started;
          globalThis.__QX_PERFORMANCE__ = globalThis.__QX_PERFORMANCE__ || {};
          const samples = globalThis.__QX_PERFORMANCE__.v2ApiMs || [];
          samples.push(elapsedMs);
          globalThis.__QX_PERFORMANCE__.v2ApiMs = samples;
        }
      });
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [enabled, evaluationId, evaluationTimestamp, symbol, timeframe, revision]);

  const retry = useCallback(() => setRevision(value => value + 1), []);
  return {...state, retry};
}
