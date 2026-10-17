import React, {useMemo} from 'react';
import {AlertTriangle, ArrowRight, BriefcaseBusiness, DatabaseZap, RefreshCw, ShieldCheck} from 'lucide-react';
import {workspaceHref} from './workspace-context';
import {isQxPortfolioFixtureEnabled} from './qx-v2-feature';
import {createPortfolioFixture, portfolioFixtureStates} from './qx-portfolio-fixtures';
import {buildPortfolioWorkspaceView} from './qx-portfolio-model';
import useQxPortfolio from './useQxPortfolio';
import useQxV2Evaluation from './useQxV2Evaluation';
import QXDataEvidence, {evidenceAttributes} from './QXDataEvidence';

export default function QXPortfolioWorkspace({context}) {
  const query = new URLSearchParams(location.search);
  const requestedFixture = query.get('portfolio_state');
  const fixtureEnabled = isQxPortfolioFixtureEnabled() && portfolioFixtureStates.includes(requestedFixture);
  const fixture = useMemo(() => fixtureEnabled ? createPortfolioFixture(requestedFixture) : null, [fixtureEnabled, requestedFixture]);
  const live = useQxPortfolio(!fixtureEnabled, {evaluationTimestamp: context.evaluation_timestamp || null});
  const linkedCandidate = !fixtureEnabled && Boolean(context.symbol && context.evaluation_timestamp);
  const evaluation = useQxV2Evaluation(context.symbol, linkedCandidate, {
    timeframe: context.timeframe || '5m',
    evaluationTimestamp: context.evaluation_timestamp || null,
  });
  const view = useMemo(
    () => buildPortfolioWorkspaceView(fixture?.snapshot || live.data, fixture?.evaluation || evaluation.data),
    [evaluation.data, fixture, live.data],
  );

  return <article className="qx-portfolio-workspace" aria-label="Canonical Portfolio Workspace"
    {...evidenceAttributes({source: view?.snapshot.source || 'canonical account snapshot', dataAsOf: view?.snapshot.dataAsOf, freshness: view?.snapshot.freshness, retrievedAt: view?.snapshot.retrievedAt})}>
    <header className="qx-portfolio-header">
      <div><span className="eyebrow">CANONICAL / READ-ONLY</span><h1><BriefcaseBusiness size={21}/> Portfolio</h1><p>Broker account positions, exposure, and Phase 10 impact. No execution.</p></div>
      <div className="qx-portfolio-header-actions">
        {fixtureEnabled && <strong className="qx-preview-badge">TEST / PREVIEW DATA - NOT LIVE</strong>}
        {!fixtureEnabled && <button type="button" onClick={live.retry} disabled={live.loading}><RefreshCw size={14} className={live.loading ? 'spin' : ''}/> Refresh snapshot</button>}
      </div>
    </header>

    {fixtureEnabled && <nav className="qx-portfolio-fixture-controls" aria-label="Portfolio fixture state">
      {portfolioFixtureStates.map(state => <a key={state} className={state === requestedFixture ? 'active' : ''} href={fixtureHref(state)}>{state.replaceAll('_', ' ')}</a>)}
    </nav>}

    {live.error && !fixtureEnabled && <Unavailable title="PORTFOLIO UNAVAILABLE" detail={live.error} retry={live.retry}/>} 
    {live.loading && !fixtureEnabled && <p className="qx-portfolio-loading" role="status"><RefreshCw className="spin" size={15}/> Loading canonical account snapshot…</p>}
    {view && <PortfolioContent view={view} context={context} candidateLoading={evaluation.loading} candidateError={evaluation.error}/>} 
  </article>;
}

function PortfolioContent({view, context, candidateLoading, candidateError}) {
  const snapshot = view.snapshot;
  return <>
    <section className={`qx-portfolio-summary qx-portfolio-panel qx-portfolio-status-${snapshot.status.toLowerCase()}`} aria-labelledby="portfolio-summary-title">
      <SectionTitle id="portfolio-summary-title" number="01" title="Account / Portfolio Summary" detail="Canonical read-only brokerage snapshot"/>
      <QXDataEvidence source={snapshot.source} dataAsOf={snapshot.dataAsOf} retrievedAt={snapshot.retrievedAt} freshness={snapshot.freshness} label="Account field evidence"/>
      <div className="qx-portfolio-summary-state"><strong>{snapshot.status}</strong><span>{snapshot.readOnly ? 'READ-ONLY' : 'BLOCKED'}</span></div>
      <div className="qx-portfolio-metrics">
        <Metric label="Total equity" value={money(snapshot.equity)}/><Metric label="Cash" value={money(snapshot.cash)}/>
        <Metric label="Buying power" value={money(snapshot.buyingPower)}/><Metric label="Gross exposure" value={money(snapshot.grossExposure)}/>
        <Metric label="Daily realized P/L" value={signedMoney(snapshot.dailyRealizedPnl)}/><Metric label="Daily unrealized P/L" value={signedMoney(snapshot.dailyUnrealizedPnl)}/>
        <Metric label="Total unrealized P/L" value={signedMoney(snapshot.totalUnrealizedPnl)}/><Metric label="Open orders" value={display(snapshot.openOrdersCount)}/>
      </div>
      <small>{display(snapshot.accountId)} · {display(snapshot.source)} · {timestamp(snapshot.dataAsOf)}</small>
    </section>

    <section className="qx-portfolio-positions qx-portfolio-panel" aria-labelledby="portfolio-positions-title">
      <SectionTitle id="portfolio-positions-title" number="02" title="Positions" detail="Canonical broker positions; never ETF constituents"/>
      {snapshot.positions.length === 0 ? <Unavailable title="NO CANONICAL POSITIONS" detail="No read-only broker positions are available for this snapshot."/> : <div className="qx-position-list" role="list">
        {snapshot.positions.map(position => <PositionRow key={`${position.symbol}-${position.assetClass}`} position={position} context={context}/>) }
      </div>}
    </section>

    <section className="qx-portfolio-risk qx-portfolio-panel" aria-labelledby="portfolio-risk-title">
      <SectionTitle id="portfolio-risk-title" number="03" title="Risk & Exposure" detail="Current account evidence; no client-side risk approval"/>
      <div className="qx-risk-grid">
        <Metric label="Gross exposure" value={money(snapshot.grossExposure)}/><Metric label="Net exposure" value={money(snapshot.netExposure)}/>
        <Metric label="Sector evidence" value={snapshot.sectorStatus}/><Metric label="Greek evidence" value={snapshot.greeksStatus}/>
        <Metric label="Portfolio delta" value={number(snapshot.greeks?.delta)}/><Metric label="Portfolio gamma" value={number(snapshot.greeks?.gamma)}/>
        <Metric label="Portfolio theta" value={number(snapshot.greeks?.theta)}/><Metric label="Portfolio vega" value={number(snapshot.greeks?.vega)}/>
      </div>
      <div className="qx-sector-list">{snapshot.sectors.length ? snapshot.sectors.map(sector => <div key={sector.sector}><span>{display(sector.sector)}</span><strong>{percent(sector.allocationPct)}</strong><small>{money(sector.marketValue)}</small></div>) : <p>Sector concentration evidence unavailable.</p>}</div>
    </section>

    <section className="qx-portfolio-attention qx-portfolio-panel" aria-labelledby="portfolio-attention-title">
      <SectionTitle id="portfolio-attention-title" number="04" title="Positions Requiring Attention" detail="Exceptions only; no autonomous management"/>
      {view.attention.length ? <div className="qx-portfolio-alert-list">{view.attention.map(code => <div key={code}><AlertTriangle size={15}/><strong>{readable(code)}</strong></div>)}</div> : <div className="qx-portfolio-clear"><ShieldCheck size={17}/><span>No canonical portfolio exceptions reported.</span></div>}
    </section>

    <section className="qx-portfolio-impact qx-portfolio-panel" aria-labelledby="portfolio-impact-title">
      <SectionTitle id="portfolio-impact-title" number="05" title="Trade / Opportunity Impact" detail="Existing canonical Phase 10 output only"/>
      {candidateLoading ? <p role="status">Loading linked canonical evaluation…</p> : candidateError ? <Unavailable title="PHASE 10 IMPACT UNAVAILABLE" detail={candidateError}/> : view.candidateImpact ? <CandidateImpact impact={view.candidateImpact}/> : <Unavailable title="NO LINKED CANDIDATE" detail="Open Portfolio from a timestamped Trade evaluation to inspect canonical Phase 10 impact."/>}
    </section>

    <section className="qx-portfolio-quality qx-portfolio-panel" aria-labelledby="portfolio-quality-title">
      <SectionTitle id="portfolio-quality-title" number="06" title="Data Quality / Partial Evidence" detail="Freshness and provenance affecting portfolio decisions"/>
      <div className="qx-quality-grid"><Metric label="Freshness" value={snapshot.freshness}/><Metric label="Sync" value={snapshot.syncStatus}/><Metric label="P/L evidence" value={snapshot.pnlStatus}/><Metric label="Greeks" value={snapshot.greeksStatus}/><Metric label="Publication" value={snapshot.publicationState}/><Metric label="Pipeline" value={snapshot.pipelineVersion}/></div>
      <details><summary>Provenance</summary><p>Account {display(snapshot.accountId)} · source {display(snapshot.source)} · sector mapping {display(snapshot.sectorMappingSource)} / {display(snapshot.sectorMappingVersion)} · retrieved {timestamp(snapshot.retrievedAt)}</p></details>
    </section>
  </>;
}

function PositionRow({position, context}) {
  const href = workspaceHref('trade', context, {symbol: position.symbol, etf: '', evaluation_timestamp: '', evaluation_id: ''});
  return <article className="qx-position-row" role="listitem">
    <div className="qx-position-symbol"><strong>{display(position.symbol)}</strong><span>{display(position.assetClass)}</span></div>
    <Metric label="Quantity" value={number(position.quantity)}/><Metric label="Market value" value={money(position.marketValue)}/>
    <Metric label="Unrealized P/L" value={signedMoney(position.unrealizedPnl)} detail={percent(position.unrealizedPnlPct)}/>
    <Metric label="Sector" value={position.sectorStatus === 'KNOWN' ? position.sectorId : position.sectorStatus}/>
    <Metric label="Concentration" value={percent(position.concentrationPct)}/>
    <a href={href}>Open Trade <ArrowRight size={13}/></a>
    <details><summary>Position details / risk evidence</summary><p>Quantity {number(position.quantity)} · entry {money(position.entryPrice)} · current {money(position.currentPrice)} · unrealized P/L {signedMoney(position.unrealizedPnl)} ({percent(position.unrealizedPnlPct)}) · sector {display(position.sectorId)} / {display(position.sectorStatus)} · Greeks {display(position.greeksStatus)} · Δ {number(position.delta)} · Γ {number(position.gamma)} · Θ {number(position.theta)} · Vega {number(position.vega)} · provider sector {display(position.providerSector)}</p></details>
  </article>;
}

function CandidateImpact({impact}) {
  return <div className="qx-candidate-impact">
    <div className="qx-candidate-impact-state"><strong>{display(impact.symbol)}</strong><span className={`qx-state qx-state-${String(impact.state || 'unavailable').toLowerCase()}`}>{display(impact.state)}</span><small>{display(impact.lifecycleState)}</small></div>
    <div className="qx-risk-grid"><Metric label="Binding constraint" value={impact.bindingConstraint}/><Metric label="Approved cap" value={number(impact.approvedContractsCap)}/><Metric label="Candidate max loss" value={money(impact.candidateTotalMaxLoss)}/><Metric label="Buying power required" value={money(impact.buyingPowerRequired)}/><Metric label="Symbol exposure" value={`${money(impact.symbolExposureBefore)} → ${money(impact.symbolExposureAfter)}`}/><Metric label="Sector exposure" value={`${money(impact.sectorExposureBefore)} → ${money(impact.sectorExposureAfter)}`}/></div>
    <details><summary>Phase 10 WHY</summary><p>{impact.reasonCodes.length ? impact.reasonCodes.map(readable).join(' · ') : 'No Phase 10 reason codes supplied.'}</p></details>
  </div>;
}

function SectionTitle({id, number: sectionNumber, title, detail}) { return <div className="qx-portfolio-section-title"><span>{sectionNumber}</span><div><h2 id={id}>{title}</h2><p>{detail}</p></div></div>; }
function Metric({label, value, detail}) { return <div className="qx-portfolio-metric"><span>{label}</span><strong>{display(value)}</strong>{detail && <small>{detail}</small>}</div>; }
function Unavailable({title, detail, retry}) { return <div className="qx-portfolio-unavailable" role="status"><DatabaseZap size={17}/><div><strong>{title}</strong><p>{detail}</p></div>{retry && <button type="button" onClick={retry}>Retry</button>}</div>; }
function display(value) { return value == null || value === '' ? 'UNAVAILABLE' : String(value); }
function number(value) { return Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: 4}) : 'UNAVAILABLE'; }
function money(value) { return Number.isFinite(value) ? value.toLocaleString(undefined, {style: 'currency', currency: 'USD', maximumFractionDigits: 2}) : 'UNAVAILABLE'; }
function signedMoney(value) { return Number.isFinite(value) ? `${value >= 0 ? '+' : '-'}${money(Math.abs(value))}` : 'UNAVAILABLE'; }
function percent(value) { return Number.isFinite(value) ? `${value.toFixed(2)}%` : 'UNAVAILABLE'; }
function timestamp(value) { if (!value) return 'UNAVAILABLE'; const parsed = new Date(value); return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString() : String(value); }
function readable(value) { return display(value).replaceAll('_', ' '); }
function fixtureHref(state) { const url = new URL(location.href); url.searchParams.set('portfolio_state', state); return `${url.pathname}${url.search}`; }
