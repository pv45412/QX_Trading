import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import QXLifecyclePanel from './QXLifecyclePanel';
import useQxV2Evaluation from './useQxV2Evaluation';
import './style.css';
import './dashboard.css';

function QxV2LiveBaseline() {
  const [symbol, setSymbol] = useState('SPY');
  const evaluation = useQxV2Evaluation(symbol, true);
  return <main className="qx-v2-preview-shell">
    <header className="qx-preview-header">
      <div><span className="eyebrow">TRACK 2C LIVE MEASUREMENT</span><h1>QX V2 Browser Baseline</h1></div>
      <strong className="qx-preview-badge">READ ONLY — NO EXECUTION</strong>
    </header>
    <div className="qx-preview-controls" role="group" aria-label="Live symbol">
      {['SPY', 'QQQ'].map(value => <button key={value} type="button" aria-pressed={symbol === value} onClick={() => setSymbol(value)}>{value}</button>)}
    </div>
    <QXLifecyclePanel
      result={evaluation.data}
      loading={evaluation.loading}
      error={evaluation.error}
      onRetry={evaluation.retry}
    />
  </main>;
}

createRoot(document.getElementById('root')).render(<QxV2LiveBaseline/>);
