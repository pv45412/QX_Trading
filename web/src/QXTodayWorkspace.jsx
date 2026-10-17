import React, {useMemo} from 'react';
import {Activity, AlertTriangle, ArrowRight, CalendarClock, RefreshCw, ShieldAlert} from 'lucide-react';
import {workspaceHref, updateWorkspaceContext} from './workspace-context';
import {
  canonicalOpportunitiesFromResponse,
  filterLegacyDiscovery,
  legacyDiscoveryFromMovers,
  tradeHandoffUpdates,
} from './qx-opportunities-model';
import {isQxTodayFixtureEnabled} from './qx-v2-feature';
import {createTodayFixture, todayFixtureStates} from './qx-today-fixtures';
import {activeTodayOpportunities, marketPulseFromEvaluations, materialHealthItems, portfolioAttentionFromSnapshot} from './qx-today-model';
import useTodayAttentionData from './useTodayAttentionData';
import QXMarketDriverPanel from './QXMarketDriverPanel';
import {adaptQxV2Evaluation} from './qx-v2-adapter';
import QXDataEvidence, {evidenceAttributes, formatEvidenceTimestamp} from './QXDataEvidence';

const horizons = ['DAY', 'SWING', 'INVEST'];
const timeframeByHorizon = {DAY: '5m', SWING: '1h', INVEST: '1d'};

export default function QXTodayWorkspace({context}) {
  const horizon = context.horizon || 'DAY';
  const timeframe = context.timeframe || timeframeByHorizon[horizon];
  const query = new URLSearchParams(location.search);
  const requestedFixture = query.get('today_state');
  const fixtureEnabled = isQxTodayFixtureEnabled() && todayFixtureStates.includes(requestedFixture);
  const live = useTodayAttentionData({enabled: !fixtureEnabled, timeframe, horizon});
  const fixture = useMemo(
    () => fixtureEnabled ? createTodayFixture(requestedFixture, horizon) : null,
    [fixtureEnabled, horizon, requestedFixture],
  );
  const evaluations = fixture?.evaluations || live.evaluations;
  const quotes = fixture?.quotes || live.quotes;
  const pulse = useMemo(() => marketPulseFromEvaluations(evaluations, quotes), [evaluations, quotes]);
  const activeOpportunities = useMemo(
    () => activeTodayOpportunities(
      fixture?.opportunities
      || canonicalOpportunitiesFromResponse(live.canonicalPayload, {horizon}),
    ),
    [fixture, horizon, live.canonicalPayload],
  );
  const legacyContext = useMemo(() => filterLegacyDiscovery(
    legacyDiscoveryFromMovers(fixture?.legacyPayload || live.legacyPayload),
    {sort: 'return_desc'},
  ).slice(0, 2), [fixture, live.legacyPayload]);
  const healthItems = useMemo(() => materialHealthItems({
    evaluations,
    operations: fixtureEnabled ? {status: 'OK', components: []} : live.operations,
    fixtureItems: [
      ...(fixture?.healthItems || []),
      ...(live.operationsError ? [{code: 'SYSTEM_HEALTH_UNAVAILABLE', label: 'System health unavailable', detail: live.operationsError, destination: 'system'}] : []),
    ],
  }), [evaluations, fixture, fixtureEnabled, live.operations, live.operationsError]);

  // Extract market driver from SPY evaluation (primary) for the drivers section
  const spyEvalData = evaluations?.SPY?.data ?? null;
  const spyCanonical = useMemo(() => adaptQxV2Evaluation(spyEvalData), [spyEvalData]);
  const spyDriver = spyCanonical?.marketDriver ?? null;
  const spyBlockedReason = spyCanonical
    ? (spyCanonical.publicationState === 'BLOCKED' ? (spyCanonical.reasons[0] ?? 'PIPELINE_BLOCKED') : null)
    : (evaluations?.SPY?.error ? 'PIPELINE_BLOCKED' : null);

  const positionAttention = fixture?.positionAttention
    || portfolioAttentionFromSnapshot(live.portfolioPayload, live.portfolioError);

  const changeHorizon = value => updateWorkspaceContext({
    horizon: value,
    timeframe: timeframeByHorizon[value],
    evaluation_timestamp: '',
    evaluation_id: '',
  });

  return <article className="qx-today-workspace" aria-label="Today Market Attention Workspace" data-fixture-state={fixtureEnabled ? requestedFixture : undefined}
    {...evidenceAttributes({source: 'canonical evaluation + live quote APIs', freshness: 'FIELD_LEVEL'})}>
    <header className="qx-today-header">
      <div>
        <span className="eyebrow">MARKET ATTENTION</span>
        <h1><Activity size={21}/> What Matters Now?</h1>
        <p>Canonical context, active opportunities, and decision-quality exceptions.</p>
      </div>
      <div className="qx-today-header-actions">
        {fixtureEnabled && <strong className="qx-preview-badge">TEST / PREVIEW DATA - NOT LIVE</strong>}
        {!fixtureEnabled && <button type="button" onClick={live.retry} disabled={live.loading}><RefreshCw size={14} className={live.loading ? 'spin' : ''}/> Refresh</button>}
      </div>
    </header>

    <div className="qx-today-horizons" role="group" aria-label="Today horizon">
      <span>Horizon</span>
      {horizons.map(value => <button key={value} type="button" aria-pressed={horizon === value} onClick={() => changeHorizon(value)}>{value}</button>)}
    </div>

    {/* 01 — MARKET PULSE */}
    <section className="qx-today-section qx-today-pulse" aria-labelledby="today-pulse-title">
      <SectionHeading number="01" title="Market Pulse" detail="SPX · SPY · QQQ live canonical context"/>
      <div className="qx-pulse-grid">
        {pulse.map(item => <PulseCard key={item.symbol} item={item}/>)}
      </div>
      {legacyContext.length > 0 && <div className="qx-today-legacy-context" aria-label="Legacy market movement context">
        <span className="qx-legacy-source-badge">LEGACY SOURCE</span>
        <div>{legacyContext.map(item => <span key={item.symbol}><strong>{item.symbol}</strong> {percent(item.return1d)} 1D</span>)}</div>
        <small>Movement context only; not a QX opportunity or market driver.</small>
      </div>}
    </section>

    {/* 02 — MARKET DRIVER */}
    <section className="qx-today-section qx-today-drivers" aria-labelledby="today-drivers-title">
      <SectionHeading number="02" title="Market Drivers" detail="Backend deterministic attribution"/>
      <QXMarketDriverPanel driver={spyDriver} symbol="SPY" compact blockedReason={spyBlockedReason}/>
    </section>

    {/* 03 — ACTIVE OPPORTUNITIES */}
    <section className="qx-today-section qx-today-opportunities" aria-labelledby="today-opportunities-title">
      <div className="qx-today-section-actions">
        <SectionHeading number="03" title="Active QX Opportunities" detail="Canonical WATCH → TRADEABLE"/>
        <a href={workspaceHref('opportunities', context, {horizon, timeframe})}>View all opportunities <ArrowRight size={13}/></a>
      </div>
      {!fixtureEnabled && live.canonicalError
        ? <AttentionState title="OPPORTUNITY SERVICE UNAVAILABLE" detail={live.canonicalError}/>
        : activeOpportunities.length === 0
          ? <AttentionState title="NO CURRENT QUALIFYING OPPORTUNITIES" detail={fixtureEnabled ? 'No canonical fixture observations require attention.' : 'No current canonical LIVE observations require attention.'} quiet/>
          : <div className="qx-today-opportunity-list" role="list">{activeOpportunities.map(row => <TodayOpportunity key={row.evaluationId || `${row.symbol}-${row.state}`} row={row} context={context}/>)}</div>}
    </section>

    {/* 04 — POSITIONS ATTENTION */}
    <section className="qx-today-section qx-today-positions" aria-labelledby="today-positions-title">
      <div className="qx-today-section-actions">
        <SectionHeading number="04" title="Positions Requiring Attention" detail="Canonical read-only account evidence"/>
        <a href={workspaceHref('portfolio', context, {horizon})}>Open Portfolio <ArrowRight size={13}/></a>
      </div>
      <div className={`qx-position-attention qx-position-${positionAttention.status.toLowerCase()}`}>
        <ShieldAlert size={18}/><div><strong>{positionAttention.status}</strong><p>{positionAttention.detail}</p></div>
      </div>
    </section>

    {/* 05 — DATA HEALTH */}
    <section className="qx-today-section qx-today-health" aria-labelledby="today-health-title">
      <div className="qx-today-section-actions">
        <SectionHeading number="05" title="Material Events / Data Health" detail="Exceptions affecting decision quality only"/>
        <a href={workspaceHref('system', context, {horizon})}>Open System <ArrowRight size={13}/></a>
      </div>
      {healthItems.length === 0
        ? <div className="qx-health-clear"><CalendarClock size={17}/><span>No material data-health exceptions reported.</span></div>
        : <div className="qx-health-alerts" role="list">{healthItems.map(item => <a key={`${item.code}-${item.label}`} role="listitem" href={workspaceHref(item.destination, context, {horizon})}><AlertTriangle size={16}/><span><strong>{item.label}</strong><small>{item.detail}</small></span><ArrowRight size={13}/></a>)}</div>}
    </section>
  </article>;
}

function SectionHeading({number, title, detail}) {
  return <div className="qx-today-section-heading"><span>{number}</span><div><h2>{title}</h2><p>{detail}</p></div></div>;
}

function PulseCard({item}) {
  const bidEvidence = item.quoteFieldEvidence?.bid;
  const askEvidence = item.quoteFieldEvidence?.ask;
  const orderBookNotPublished = bidEvidence?.availability === 'NOT_PUBLISHED'
    || askEvidence?.availability === 'NOT_PUBLISHED';
  return <article className={`qx-pulse-card qx-pulse-${item.status.toLowerCase()}`}
    {...evidenceAttributes({source: `${source(item.quoteSource)} + ${source(item.barSource)}`, dataAsOf: item.quoteTimestamp || item.barDataAsOf, freshness: `${display(item.quoteFreshness)} / ${display(item.barFreshness)}`})}>
    <div className="qx-pulse-card-heading">
      <strong>{item.symbol}</strong>
      <span className={`qx-pulse-status-badge qx-pulse-status-${item.status.toLowerCase()}`}>{item.status}</span>
    </div>
    <div className="qx-pulse-quote">
      <strong>{marketPrice(item.quoteLast)}</strong>
      <span className={changeClass(item.quoteChangePct)}>{percentage(item.quoteChangePct)}</span>
    </div>
    <dl className="qx-pulse-market-data" aria-label={`${item.symbol} live quote`}>
      <div><dt>Bid</dt><dd title={fieldEvidenceDetail(bidEvidence)}>{marketPrice(item.quoteBid, bidEvidence)}</dd></div>
      <div><dt>Ask</dt><dd title={fieldEvidenceDetail(askEvidence)}>{marketPrice(item.quoteAsk, askEvidence)}</dd></div>
      <div><dt>Volume</dt><dd>{integer(item.quoteVolume)}</dd></div>
    </dl>
    {orderBookNotPublished && <p className="qx-pulse-field-note">
      {source(item.quoteSource)} returned an {display(item.quoteAssetType)} snapshot without an executable order book; bid and ask are not published.
    </p>}
    <dl className="qx-pulse-canonical" aria-label={`${item.symbol} canonical context`}>
      <div><dt>Direction</dt><dd>{display(item.direction)}</dd></div>
      <div><dt>Regime</dt><dd>{display(item.regime)}</dd></div>
      <div><dt>Volatility</dt><dd>{display(item.volatility)}</dd></div>
      <div><dt>Session</dt><dd>{display(item.session)}</dd></div>
    </dl>
    <QXDataEvidence source={`${source(item.quoteSource)} + ${source(item.barSource)}`} dataAsOf={item.quoteTimestamp || item.barDataAsOf}
      freshness={`${display(item.quoteFreshness)} / ${display(item.barFreshness)}`} label={`${item.symbol} field evidence`}/>
    {item.reason && !item.evaluationTimestamp && (
      <p className="qx-pulse-reason">{item.reason}</p>
    )}
    <details className="qx-pulse-provenance-details">
      <summary>Data provenance</summary>
      <dl className="qx-pulse-provenance" aria-label={`${item.symbol} data provenance`}>
        <div><dt>Quote Source</dt><dd>{source(item.quoteSource)}</dd></div>
        <div><dt>Asset Type</dt><dd>{display(item.quoteAssetType)}</dd></div>
        <div><dt>Bid Field</dt><dd>{fieldEvidenceDetail(bidEvidence)}</dd></div>
        <div><dt>Ask Field</dt><dd>{fieldEvidenceDetail(askEvidence)}</dd></div>
        <div><dt>Quote Mode</dt><dd>{realtime(item.quoteRealtime)}</dd></div>
        <div><dt>Quote Timestamp</dt><dd>{timestamp(item.quoteTimestamp)}</dd></div>
        <div><dt>Quote Freshness</dt><dd>{display(item.quoteFreshness)}</dd></div>
        <div><dt>Bar Source</dt><dd>{source(item.barSource)}</dd></div>
        <div><dt>Bar Data As Of</dt><dd>{timestamp(item.barDataAsOf)}</dd></div>
        <div><dt>Bar Freshness</dt><dd>{display(item.barFreshness)}</dd></div>
        {item.evaluationTimestamp && <div><dt>Evaluation</dt><dd>{timestamp(item.evaluationTimestamp)}</dd></div>}
      </dl>
    </details>
  </article>;
}

function TodayOpportunity({row, context}) {
  const href = new URL(workspaceHref('trade', context, tradeHandoffUpdates(row)));
  if (row.fixtureState) href.searchParams.set('fixture_state', row.fixtureState);
  return <article className="qx-today-opportunity" role="listitem">
    <div className="qx-today-opportunity-symbol"><strong>{row.symbol}</strong><span>{row.horizon} · {display(row.timeframe)}</span></div>
    <span className={`qx-state qx-state-${row.state.toLowerCase()}`}>{row.state}</span>
    <div><span>Direction</span><strong>{display(row.direction)}</strong></div>
    <div><span>Trigger / risk</span><strong>{price(row.trigger)} / {price(row.invalidation)}</strong></div>
    <div><span>Tradeability</span><strong>{display(row.tradeability)}</strong></div>
    <div><span>Freshness</span><strong>{timestamp(row.evaluationTimestamp)}</strong></div>
    <a href={`${href.pathname}${href.search}`}>Open Trade <ArrowRight size={13}/></a>
  </article>;
}

function AttentionState({title, detail, quiet = false}) {
  return <div className={`qx-today-attention-state${quiet ? ' qx-today-attention-quiet' : ''}`} role="status">
    <AlertTriangle size={18}/><div><strong>{title}</strong><p>{detail}</p></div>
  </div>;
}

function display(value) {
  return value == null || value === '' ? 'UNAVAILABLE' : String(value);
}

function price(value) {
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : 'UNAVAILABLE';
}

function percent(value) {
  return Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%` : 'UNAVAILABLE';
}

function marketPrice(value, evidence = null) {
  if (Number.isFinite(value)) return value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return evidence?.availability === 'NOT_PUBLISHED' ? 'NOT PUBLISHED' : 'UNAVAILABLE';
}

function percentage(value) {
  return Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%` : 'UNAVAILABLE';
}

function integer(value) {
  return Number.isFinite(value) ? Math.trunc(value).toLocaleString() : 'UNAVAILABLE';
}

function source(value) {
  return value == null || value === '' ? 'UNAVAILABLE' : String(value).toUpperCase();
}

function realtime(value) {
  return value === true ? 'REALTIME' : value === false ? 'DELAYED' : 'UNAVAILABLE';
}

function fieldEvidenceDetail(evidence) {
  if (!evidence || typeof evidence !== 'object') return 'UNAVAILABLE';
  return [source(evidence.source), display(evidence.availability), evidence.reason_code ? display(evidence.reason_code) : null]
    .filter(Boolean)
    .join(' · ');
}

function changeClass(value) {
  return Number.isFinite(value) ? value >= 0 ? 'positive' : 'negative' : '';
}

function timestamp(value) {
  return formatEvidenceTimestamp(value);
}
