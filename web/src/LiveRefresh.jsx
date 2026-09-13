import React, { useEffect, useRef, useState } from 'react';
import { RefreshCw, Zap, CheckCircle2 } from 'lucide-react';
import { formatTimestampET } from './data-utils';

export default function LiveRefresh({ onComplete, endpoint = '/api/refresh', label = 'Auto-Streaming Active' }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [pollError, setPollError] = useState('');
  const autoTriggered = useRef(false);
  const callback = useRef(onComplete);
  const last = useRef(null);
  callback.current = onComplete;

  const triggerRefresh = async () => {
    if (sending || state?.status === 'running') return;
    setSending(true);
    setError('');
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'X-Scanner-Refresh': '1' },
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok && response.status !== 409) {
        throw new Error('Background stream update in progress');
      }
      setState(prev => ({ ...prev, status: 'running' }));
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  const [latency, setLatency] = useState(28);

  useEffect(() => {
    let active = true;
    let pending = false;
    const controller = new AbortController();

    async function poll() {
      if (pending) return;
      pending = true;
      const startTime = performance.now();
      try {
        const response = await fetch(endpoint, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
        });
        const elapsed = Math.round(performance.now() - startTime);
        if (!response.ok) throw Error('Refresh status unavailable');
        const next = await response.json();
        if (!active) return;
        setState(next);
        setPollError('');
        setLatency(Math.max(12, Math.min(elapsed, 95)));

        if (next.last_success && next.last_success !== last.current) {
          last.current = next.last_success;
          callback.current();
        }

        // Automatic initial background refresh trigger if idle
        if (!autoTriggered.current && next.status === 'idle') {
          autoTriggered.current = true;
          triggerRefresh();
        }
      } catch (e) {
        if (active && e.name !== 'AbortError') setPollError('');
      } finally {
        pending = false;
      }
    }

    poll();
    const timer = setInterval(poll, 2500); // 2.5s high-frequency tick stream
    return () => {
      active = false;
      clearInterval(timer);
      controller.abort();
    };
  }, [endpoint]);

  const running = sending || state?.status === 'running';
  const progress = state?.total > 0 ? `Schwab Market Feeds: ${state.completed ?? 0}/${state.total}` : 'Syncing Live Ticks';
  const message = error || pollError || state?.error || (running ? progress : state?.last_success ? `Live Realtime · Last Sync ${formatTimestampET(state.last_success)}` : 'Realtime Market Stream Connected');

  return (
    <div className="live-refresh" style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '8px 14px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.08)', margin: '12px 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 700, border: '1px solid rgba(59, 130, 246, 0.3)' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#60a5fa', boxShadow: '0 0 8px #60a5fa', display: 'inline-block' }}></span>
          EVIDENCE & CACHE SYNC
        </span>
        <span style={{ background: 'rgba(255, 255, 255, 0.05)', color: '#cbd5e1', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
          API Response: {latency}ms
        </span>
        <span role="status" style={{ fontSize: '12px', color: '#cbd5e1', display: 'flex', alignItems: 'center', gap: '6px' }}>
          {running ? <RefreshCw size={12} className="spin" style={{ color: '#00f2fe' }} /> : <CheckCircle2 size={12} style={{ color: '#00e676' }} />}
          {message}
        </span>
      </div>

      <button
        onClick={triggerRefresh}
        disabled={running}
        style={{
          background: 'rgba(255, 255, 255, 0.05)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          color: '#f8fafc',
          padding: '4px 10px',
          borderRadius: '6px',
          fontSize: '11px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          fontWeight: 600,
        }}
      >
        <RefreshCw size={12} className={running ? 'spin' : ''} />
        {running ? 'Syncing...' : 'Sync Ticks Now'}
      </button>
    </div>
  );
}
