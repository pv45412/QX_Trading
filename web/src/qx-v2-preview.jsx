import React, {useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import QXLifecyclePanel from './QXLifecyclePanel';
import {isQxV2UiEnabled} from './qx-v2-feature';
import {createQxV2PreviewFixture, previewStates} from './qx-v2-fixtures';
import './style.css';
import './dashboard.css';

function QxV2Preview() {
  const query = new URLSearchParams(location.search);
  const initialState = previewStates.includes(query.get('state')) ? query.get('state') : 'NO_SETUP';
  const [state, setState] = useState(initialState);
  const [symbol, setSymbol] = useState('SPY');
  const enabled = isQxV2UiEnabled();
  const result = useMemo(() => createQxV2PreviewFixture(state, symbol), [state, symbol]);

  return <main className="qx-v2-preview-shell">
    <header className="qx-preview-header">
      <div><span className="eyebrow">TRACK 2F REVIEW SURFACE</span><h1>QX V2 Lifecycle Preview</h1></div>
      <strong className="qx-preview-badge">TEST / PREVIEW DATA — NOT LIVE</strong>
    </header>
    {!enabled ? <p className="qx-preview-disabled" role="status">QX V2 UI feature flag is OFF.</p> : <>
      <div className="qx-preview-controls">
        <label>Fixture state<select aria-label="Fixture state" value={state} onChange={event => setState(event.target.value)}>
          {previewStates.map(value => <option key={value}>{value}</option>)}
        </select></label>
        <div role="group" aria-label="Fixture symbol">
          {['SPY', 'QQQ'].map(value => <button key={value} type="button" aria-pressed={symbol === value} onClick={() => setSymbol(value)}>{value}</button>)}
        </div>
      </div>
      <QXLifecyclePanel result={result} loading={false} error="" onRetry={() => {}}/>
    </>}
  </main>;
}

createRoot(document.getElementById('root')).render(<QxV2Preview/>);
