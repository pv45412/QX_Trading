import {useCallback, useEffect, useState} from 'react';
import {fetchQxPortfolio} from './qx-portfolio-client';

export default function useQxPortfolio(enabled, {evaluationTimestamp = null} = {}) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({data: null, error: '', loading: false});

  useEffect(() => {
    if (!enabled) {
      setState({data: null, error: '', loading: false});
      return undefined;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let active = true;
    setState({data: null, error: '', loading: true});
    fetchQxPortfolio({signal: controller.signal, evaluationTimestamp})
      .then(data => { if (active) setState({data, error: '', loading: false}); })
      .catch(error => {
        if (active) setState({
          data: null,
          loading: false,
          error: error.name === 'AbortError' ? 'Canonical Portfolio request timed out.' : error.message,
        });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [enabled, evaluationTimestamp, revision]);

  const retry = useCallback(() => setRevision(value => value + 1), []);
  return {...state, retry};
}
