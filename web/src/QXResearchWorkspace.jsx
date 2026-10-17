import React, {lazy, Suspense, useEffect, useState} from 'react';
import {ArrowRight, BarChart3, BookOpen, BriefcaseBusiness, FlaskConical, History, Layers3, Search} from 'lucide-react';
import {workspaceHref, updateWorkspaceContext} from './workspace-context';
import {isQxResearchFixtureEnabled} from './qx-v2-feature';
import {buildBacktestView, buildResearchSnapshot, researchModeForRoute, researchModes} from './qx-research-model';
import {fetchResearchSnapshot, runResearchBacktest} from './qx-research-client';
import useAnalytics from './useAnalytics';
import QXDataEvidence, {evidenceAttributes, formatEvidenceTimestamp} from './QXDataEvidence';

const Holdings = lazy(() => import('./Holdings'));
const MoversWorkspace = lazy(() => import('./MoversWorkspace'));
const QXOptionsIdeas = lazy(() => import('./QXOptionsIdeas'));
const QXStrategyWorkspaces = lazy(() => import('./QXStrategyWorkspaces'));
const ReferenceRanking = lazy(() => import('./ReferenceRanking'));
const RSLine = lazy(() => import('./RSLine'));

const sectorEtfs = ['XLC', 'XLY', 'XLP', 'XLE', 'XLF', 'XLV', 'XLI', 'XLK', 'XLB', 'XLRE', 'XLU'];

export default function QXResearchWorkspace({context, route}) {
  const query = new URLSearchParams(location.search);
  const mode = researchModeForRoute(route?.page, context.research_mode);
  const symbol = context.symbol || context.etf || 'SPY';
  const fixtureEnabled = isQxResearchFixtureEnabled() && query.get('research_fixture') === '1';

  return <article className="qx-research-workspace" aria-label="Research Workspace"
    {...evidenceAttributes({source: 'QX research endpoints', freshness: 'DECLARED_PER_PANEL'})}>
    <header className="qx-research-header">
      <div>
        <span className="eyebrow">RESEARCH / ANALYTICAL DEPTH</span>
        <h1><BookOpen size={22}/> Research</h1>
        <p>Source-backed context, modeled exploration, and historical validation. Canonical lifecycle decisions remain in Trade.</p>
      </div>
      <div className="qx-research-header-badges">
        {fixtureEnabled && <strong className="qx-preview-badge">TEST / PREVIEW DATA - NOT LIVE</strong>}
        {route?.legacy && <SourceBadge labels={['LEGACY']}/>} 
      </div>
    </header>

    <ResearchActions context={context} symbol={symbol} mode={mode}/>
    <nav className="qx-research-modes" aria-label="Research modes">
      {researchModes.map(item => <a key={item.id} className={item.id === mode ? 'active' : ''}
        aria-current={item.id === mode ? 'page' : undefined}
        href={workspaceHref('research', context, {research_mode: item.id, evaluation_timestamp: '', evaluation_id: '', snapshot: ''})}>
        <span>{item.shortLabel}</span><small>{item.label}</small>
      </a>)}
    </nav>

    <div className="qx-research-stage">
      {mode === 'symbol' && <SymbolResearch symbol={symbol}/>} 
      {mode === 'etf_sector' && <EtfSectorResearch context={context}/>} 
      {mode === 'relative_strength' && <RelativeStrengthResearch context={context}/>} 
      {mode === 'options_strategy' && <OptionsStrategyResearch/>} 
      {mode === 'historical' && <HistoricalResearch symbol={symbol}/>} 
      {mode === 'long_term' && <LongTermResearch symbol={symbol}/>} 
    </div>
  </article>;
}

function ResearchActions({context, symbol, mode}) {
  const [input, setInput] = useState(symbol);
  useEffect(() => setInput(symbol), [symbol]);
  const submit = event => {
    event.preventDefault();
    const next = input.trim().toUpperCase();
    if (/^[A-Z0-9^/][A-Z0-9.^=/\-]{0,19}$/.test(next)) {
      updateWorkspaceContext({symbol: next, research_mode: mode, evaluation_timestamp: '', evaluation_id: '', snapshot: ''});
    }
  };
  const handoff = {symbol, horizon: context.horizon || 'SWING', timeframe: context.timeframe || '1d',
    etf: '', evaluation_timestamp: '', evaluation_id: '', snapshot: '', as_of: '', account_id: '', research_mode: ''};
  return <section className="qx-research-actions" aria-label="Research context and handoffs">
    <form onSubmit={submit}><label>Research symbol<input aria-label="Research symbol" value={input} onChange={event => setInput(event.target.value)}/></label><button type="submit"><Search size={14}/> Load research</button></form>
    <div className="qx-research-handoffs">
      <a className="primary" href={workspaceHref('trade', context, handoff)}>Open in Trade <ArrowRight size={13}/></a>
      <a href={workspaceHref('portfolio', context, {...handoff, research_mode: ''})}>Check in Portfolio <BriefcaseBusiness size={13}/></a>
    </div>
    <p><strong>Handoff rule:</strong> Research sends symbol and explicit horizon/timeframe preferences only. Trade creates a fresh canonical evaluation.</p>
  </section>;
}

function SymbolResearch({symbol}) {
  const research = useResearchSnapshot(symbol, true);
  const snapshot = buildResearchSnapshot(research.data, symbol);
  return <>
    <ResearchTitle icon={Search} title="Symbol Research" detail="Why the instrument matters and what source-backed history currently shows"/>
    <ResearchPanel title={`${symbol} market and structure context`} labels={snapshot.sourceClass === 'SOURCE_BACKED' ? ['SOURCE-BACKED'] : ['UNAVAILABLE']}>
      <SnapshotState research={research} snapshot={snapshot}/>
    </ResearchPanel>
    <ResearchPanel title="Research interpretation boundary" labels={['STATIC']}>
      <p className="qx-research-boundary">Structure, price history, and relative context are research evidence only. This workspace does not publish WATCH, ARMED, TRIGGERED, TRADEABLE, options suitability, or portfolio approval.</p>
    </ResearchPanel>
  </>;
}

function EtfSectorResearch({context}) {
  const initial = sectorEtfs.includes(context.etf) ? context.etf : 'XLK';
  const [etf, setEtf] = useState(initial);
  const [lineStatus, setLineStatus] = useState('LOADING');
  const [holdingsStatus, setHoldingsStatus] = useState('LOADING');
  return <>
    <ResearchTitle icon={Layers3} title="ETF / Sector Research" detail="Fund-relative history and constituent concentration; never broker Portfolio positions"/>
    <div className="qx-research-inline-control"><label>Sector ETF<select aria-label="Research sector ETF" value={etf} onChange={event => {
      setEtf(event.target.value); updateWorkspaceContext({etf: event.target.value, research_mode: 'etf_sector'});
    }}>{sectorEtfs.map(value => <option key={value}>{value}</option>)}</select></label></div>
    <ResearchPanel title={`${etf} relative-strength history`} labels={sourceLabels(lineStatus)}>
      <Suspense fallback={<Loading/>}><RSLine symbol={etf} onAvailabilityChange={setLineStatus}/></Suspense>
    </ResearchPanel>
    <ResearchPanel title={`${etf} constituents`} labels={sourceLabels(holdingsStatus)} extra="ETF CONSTITUENTS / NOT PORTFOLIO">
      <Suspense fallback={<Loading/>}><Holdings symbol={etf} onAvailabilityChange={setHoldingsStatus}/></Suspense>
    </ResearchPanel>
  </>;
}

function RelativeStrengthResearch({context}) {
  const [revision, setRevision] = useState(0);
  const analytics = useAnalytics(revision);
  const symbol = context.etf || 'XLK';
  const select = value => updateWorkspaceContext({etf: value, symbol: value, research_mode: 'relative_strength'});
  const labels = sourceLabels(analytics.data ? 'SOURCE_BACKED' : analytics.error && !analytics.busy ? 'UNAVAILABLE' : 'LOADING');
  return <>
    <ResearchTitle icon={BarChart3} title="Relative Strength / Rotation" detail="Sector ranking, rotation, and market movers from cached source data"/>
    <ResearchPanel title="Sector ranking and rotation" labels={labels}>
      <Suspense fallback={<Loading/>}><ReferenceRanking data={analytics.data} error={analytics.error} busy={analytics.busy} onRetry={() => setRevision(value => value + 1)} onSelect={select} symbol={symbol}/></Suspense>
    </ResearchPanel>
    <ResearchPanel title="Market movers context" labels={labels}>
      <Suspense fallback={<Loading/>}><MoversWorkspace data={analytics.data} revision={revision} onSelect={select}/></Suspense>
    </ResearchPanel>
  </>;
}

function OptionsStrategyResearch() {
  return <>
    <ResearchTitle icon={FlaskConical} title="Options / Strategy Research" detail="Modeled contracts, hypothetical legs, and payoff exploration"/>
    <ResearchPanel title="Exploratory options ideas" labels={['MODELED', 'LEGACY']} extra="NOT CANONICAL PHASE 9">
      <Suspense fallback={<Loading/>}><QXOptionsIdeas/></Suspense>
    </ResearchPanel>
    <ResearchPanel title="Strategy and payoff laboratory" labels={['MODELED', 'STATIC']} extra="SIMULATED / RESEARCH_ONLY">
      <Suspense fallback={<Loading/>}><QXStrategyWorkspaces/></Suspense>
    </ResearchPanel>
  </>;
}

function HistoricalResearch({symbol}) {
  const research = useResearchSnapshot(symbol, true);
  const snapshot = buildResearchSnapshot(research.data, symbol);
  return <>
    <ResearchTitle icon={History} title="Historical / Backtest" detail="Historical structure and simulated outcomes kept separate from live canonical state"/>
    <ResearchPanel title={`${symbol} historical structure context`} labels={[...sourceLabels(snapshot.sourceClass === 'SOURCE_BACKED' ? 'SOURCE_BACKED' : research.loading ? 'LOADING' : 'UNAVAILABLE'), 'HISTORICAL']}>
      <SnapshotState research={research} snapshot={snapshot}/>
    </ResearchPanel>
    <ResearchPanel title="Rectangle breakout backtest" labels={['HISTORICAL', 'SIMULATED']} extra="RESEARCH_ONLY">
      <BacktestResearch symbol={symbol}/>
    </ResearchPanel>
  </>;
}

function LongTermResearch({symbol}) {
  const research = useResearchSnapshot(symbol, true);
  const snapshot = buildResearchSnapshot(research.data, symbol);
  const [thesis, setThesis] = useState('');
  return <>
    <ResearchTitle icon={BookOpen} title="Long-Term Thesis" detail="Durable research context without buy/sell recommendations"/>
    <ResearchPanel title={`${symbol} longer-horizon context`} labels={snapshot.sourceClass === 'SOURCE_BACKED' ? ['SOURCE-BACKED'] : ['UNAVAILABLE']}>
      <SnapshotState research={research} snapshot={snapshot}/>
    </ResearchPanel>
    <ResearchPanel title="Thesis notebook" labels={['USER-ENTERED']} extra="LOCAL SESSION / NOT PERSISTED">
      <label className="qx-thesis-field">Research thesis<textarea value={thesis} onChange={event => setThesis(event.target.value)} placeholder="Record assumptions, evidence to verify, invalidating facts, and review cadence..."/></label>
      <p className="qx-research-boundary">This note is not saved and is not a buy/sell recommendation. Fundamental and valuation fields remain unavailable until a source-backed contract exists.</p>
    </ResearchPanel>
  </>;
}

function BacktestResearch({symbol}) {
  const [state, setState] = useState({data: null, loading: false, error: ''});
  const run = async () => {
    const controller = new AbortController();
    setState({data: null, loading: true, error: ''});
    try {
      const payload = await runResearchBacktest(symbol, {signal: controller.signal});
      setState({data: buildBacktestView(payload), loading: false, error: ''});
    } catch (error) {
      setState({data: null, loading: false, error: error.message});
    }
  };
  const result = state.data;
  return <div className="qx-backtest-research">
    <div><p>Runs the existing cached-bar rectangle backtest. Results describe historical simulation only and never alter live confidence or rules.</p><button type="button" onClick={run} disabled={state.loading}>{state.loading ? 'Running historical simulation...' : `Run ${symbol} backtest`}</button></div>
    {state.error && <p role="alert">{state.error}</p>}
    {result && <><div className="qx-research-metrics"><Metric label="Symbol" value={result.symbol}/><Metric label="Historical trades" value={result.totalTrades}/><Metric label="Historical win rate" value={percent(result.winRate)}/><Metric label="Average historical return" value={percent(result.averageReturnPct)}/></div><p className="qx-research-boundary">Historical success is not current trade confidence and is not promoted into the canonical lifecycle.</p></>}
  </div>;
}

function SnapshotState({research, snapshot}) {
  if (research.loading) return <Loading/>;
  if (research.error) return <p role="alert">{research.error}</p>;
  if (snapshot.status === 'UNAVAILABLE') return <div className="qx-research-unavailable" role="status"><strong>RESEARCH DATA UNAVAILABLE</strong><span>{readable(snapshot.reasonCode)}</span></div>;
  return <>
    <div className="qx-research-metrics">
      <Metric label="Last price" value={money(snapshot.lastPrice)}/><Metric label="Historical trend" value={snapshot.trend}/>
      <Metric label="Structure score" value={number(snapshot.structureScore)}/><Metric label="Latest BOS" value={snapshot.latestBos}/>
      <Metric label="Latest CHoCH" value={snapshot.latestChoch}/><Metric label="Active FVG records" value={snapshot.activeFvgCount}/>
    </div>
    <QXDataEvidence source={snapshot.source} dataAsOf={snapshot.dataAsOf} retrievedAt={snapshot.retrievedAt} freshness="HISTORICAL_SOURCE_BACKED" label="Research field evidence"/>
    <p className="qx-research-provenance">Source {display(snapshot.source)} · data as of {timestamp(snapshot.dataAsOf)} · retrieved {timestamp(snapshot.retrievedAt)}</p>
  </>;
}

function useResearchSnapshot(symbol, enabled) {
  const [state, setState] = useState({data: null, loading: enabled, error: ''});
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    setState({data: null, loading: true, error: ''});
    fetchResearchSnapshot(symbol, {signal: controller.signal})
      .then(data => setState({data, loading: false, error: ''}))
      .catch(error => { if (error.name !== 'AbortError') setState({data: null, loading: false, error: error.message}); });
    return () => controller.abort();
  }, [enabled, symbol]);
  return state;
}

function ResearchTitle({icon: Icon, title, detail}) { return <div className="qx-research-mode-title"><Icon size={18}/><div><h2>{title}</h2><p>{detail}</p></div></div>; }
function ResearchPanel({title, labels, extra, children}) { const source = labels.join(' + '); return <section className="qx-research-panel" {...evidenceAttributes({source, freshness: source})}><header><div><h3>{title}</h3>{extra && <small>{extra}</small>}</div><SourceBadge labels={labels}/></header>{children}</section>; }
function SourceBadge({labels}) { return <div className="qx-source-badges">{labels.map(label => <span key={label} className={`qx-source-${label.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}`}>{label}</span>)}</div>; }
function Metric({label, value}) { return <div><span>{label}</span><strong>{display(value)}</strong></div>; }
function Loading() { return <p className="qx-research-loading" role="status">Loading research evidence...</p>; }
function display(value) { return value == null || value === '' ? 'UNAVAILABLE' : String(value); }
function readable(value) { return display(value).replaceAll('_', ' '); }
function number(value) { return Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: 4}) : 'UNAVAILABLE'; }
function money(value) { return Number.isFinite(value) ? value.toLocaleString(undefined, {style: 'currency', currency: 'USD', maximumFractionDigits: 2}) : 'UNAVAILABLE'; }
function percent(value) { return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : 'UNAVAILABLE'; }
function timestamp(value) { return formatEvidenceTimestamp(value); }
function sourceLabels(status) { return [status === 'SOURCE_BACKED' ? 'SOURCE-BACKED' : status === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'LOADING']; }
