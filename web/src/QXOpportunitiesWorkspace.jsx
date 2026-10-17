import React, {useEffect, useMemo, useState} from 'react';
import {ArrowRight, Binoculars, RefreshCw, Search, TriangleAlert} from 'lucide-react';
import {workspaceHref, updateWorkspaceContext} from './workspace-context';
import QXDataEvidence, {evidenceAttributes} from './QXDataEvidence';
import {isQxOpportunitiesFixtureEnabled} from './qx-v2-feature';
import {
  fetchCanonicalOpportunities,
  fetchLegacyOpportunityDiscovery,
  scanCanonicalOpportunities,
} from './qx-opportunities-client';
import {createCanonicalOpportunityFixtures} from './qx-opportunities-fixtures';
import {
  filterCanonicalOpportunities,
  filterLegacyDiscovery,
  canonicalOpportunitiesFromResponse,
  legacyDiscoveryFromMovers,
  opportunityStates,
  tradeHandoffUpdates,
} from './qx-opportunities-model';

const horizons = ['DAY', 'SWING', 'INVEST'];
const timeframeByHorizon = {DAY: '5m', SWING: '1h', INVEST: '1d'};
const directionOptions = ['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL', 'UNAVAILABLE'];
const terminalStates = new Set(['BLOCKED', 'NO_SETUP', 'NOT_TRADEABLE', 'EXPIRED', 'OPTIONS_NOT_SUITABLE', 'PORTFOLIO_VETOED']);

export default function QXOpportunitiesWorkspace({context}) {
  const horizon = context.horizon || 'DAY';
  const timeframe = context.timeframe || timeframeByHorizon[horizon];
  const fixtureEnabled = isQxOpportunitiesFixtureEnabled();
  const [query, setQuery] = useState('');
  const [stateFilter, setStateFilter] = useState('ALL');
  const [directionFilter, setDirectionFilter] = useState('ALL');
  const [sort, setSort] = useState('evaluation_desc');
  const [legacyPayload, setLegacyPayload] = useState(null);
  const [legacyError, setLegacyError] = useState('');
  const [legacyLoading, setLegacyLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [canonicalPayload, setCanonicalPayload] = useState(null);
  const [canonicalError, setCanonicalError] = useState('');
  const [canonicalLoading, setCanonicalLoading] = useState(!fixtureEnabled);
  const [paginationError, setPaginationError] = useState('');
  const [paginationLoading, setPaginationLoading] = useState(false);
  const [scanStatus, setScanStatus] = useState({state: 'idle', completed: 0, total: 0, message: ''});
  const canonicalRequest = useMemo(() => ({
    timeframe,
    states: ['ALL', 'ACTIVE'].includes(stateFilter) ? undefined : [stateFilter],
    direction: directionFilter === 'ALL' ? undefined : directionFilter,
    horizonContext: horizon,
    includeTerminal: stateFilter === 'ALL' || terminalStates.has(stateFilter),
    includeBlocked: stateFilter === 'ALL' || stateFilter === 'BLOCKED',
    freshOnly: true,
    limit: 25,
  }), [directionFilter, horizon, stateFilter, timeframe]);

  useEffect(() => {
    if (fixtureEnabled) {
      setCanonicalLoading(false);
      setCanonicalError('');
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    setCanonicalLoading(true);
    setCanonicalError('');
    setPaginationError('');
    setCanonicalPayload(null);
    fetchCanonicalOpportunities({signal: controller.signal, ...canonicalRequest})
      .then(payload => { if (active) setCanonicalPayload(payload); })
      .catch(error => {
        if (active && error.name !== 'AbortError') setCanonicalError(error.message);
      })
      .finally(() => { if (active) setCanonicalLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [attempt, canonicalRequest, fixtureEnabled]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLegacyLoading(true);
    setLegacyError('');
    fetchLegacyOpportunityDiscovery({signal: controller.signal})
      .then(payload => { if (active) setLegacyPayload(payload); })
      .catch(error => { if (active && error.name !== 'AbortError') setLegacyError(error.message); })
      .finally(() => { if (active) setLegacyLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [attempt]);

  const canonicalRows = useMemo(
    () => fixtureEnabled
      ? createCanonicalOpportunityFixtures(horizon)
      : canonicalOpportunitiesFromResponse(canonicalPayload, {horizon}),
    [canonicalPayload, fixtureEnabled, horizon],
  );
  const filteredCanonical = useMemo(() => filterCanonicalOpportunities(canonicalRows, {
    horizon, state: stateFilter, direction: directionFilter, query, sort,
  }), [canonicalRows, horizon, stateFilter, directionFilter, query, sort]);
  const legacyRows = useMemo(() => filterLegacyDiscovery(
    legacyDiscoveryFromMovers(legacyPayload),
    {query, sort: sort === 'return_desc' ? sort : 'symbol'},
  ).slice(0, 24), [legacyPayload, query, sort]);
  const canonicalBars = canonicalRows.flatMap(row => row.dependencies || []).find(item => item.name === 'bars') || null;

  const changeHorizon = value => updateWorkspaceContext({
    horizon: value,
    timeframe: timeframeByHorizon[value],
    evaluation_timestamp: '',
    evaluation_id: '',
  });

  const loadMore = async () => {
    const cursor = canonicalPayload?.next_cursor;
    if (!cursor || paginationLoading) return;
    setPaginationLoading(true);
    setPaginationError('');
    try {
      const nextPage = await fetchCanonicalOpportunities({...canonicalRequest, cursor});
      setCanonicalPayload(current => mergeOpportunityPages(current, nextPage));
    } catch (error) {
      setPaginationError(error.message);
    } finally {
      setPaginationLoading(false);
    }
  };

  const runLiveScan = async () => {
    const symbols = legacyRows.map(row => row.symbol);
    if (!symbols.length || scanStatus.state === 'running') return;
    setScanStatus({state: 'running', completed: 0, total: Math.min(8, symbols.length), message: 'Starting audited evaluations...'});
    try {
      const results = await scanCanonicalOpportunities({
        symbols,
        timeframe,
        limit: 8,
        onProgress: progress => setScanStatus({
          state: 'running',
          ...progress,
          message: `Evaluating ${progress.symbol}...`,
        }),
      });
      const succeeded = results.filter(result => result.evaluation).length;
      const active = results.filter(result => result.evaluation && !terminalStates.has(result.evaluation.current_lifecycle_state)).length;
      const failed = results.length - succeeded;
      setScanStatus({
        state: failed === results.length ? 'error' : 'complete',
        completed: results.length,
        total: results.length,
        message: `${succeeded} evaluated, ${active} active${failed ? `, ${failed} unavailable` : ''}.`,
      });
      if (succeeded && active === 0) setStateFilter('ALL');
      setAttempt(value => value + 1);
    } catch (error) {
      setScanStatus({state: 'error', completed: 0, total: 0, message: error.message});
    }
  };

  const clearFilters = () => {
    setQuery('');
    setStateFilter('ACTIVE');
    setDirectionFilter('ALL');
    setSort('evaluation_desc');
  };

  const canonicalFiltersApplied = stateFilter !== 'ACTIVE' || directionFilter !== 'ALL' || query.trim() !== '';
  const canonicalEmptyDetail = canonicalRows.length
    ? `${canonicalRows.length} current evaluation${canonicalRows.length === 1 ? '' : 's'} do not match the selected filters.`
    : canonicalFiltersApplied
      ? `No current canonical evaluations match ${stateFilter === 'ACTIVE' ? 'the selected' : stateFilter} filters. Select ALL or clear filters to inspect other current outcomes.`
    : stateFilter === 'ACTIVE'
      ? 'No current ACTIVE evaluations match. Select ALL to inspect terminal or blocked outcomes, or evaluate the current live movers.'
    : scanStatus.state === 'complete'
      ? 'The live scan completed without a current qualifying setup. Select ALL to inspect evaluated outcomes.'
      : 'No live evaluations are published for this horizon yet. Evaluate the current live movers to populate audited outcomes.';

  return <article className="qx-opportunities-workspace" aria-label="Canonical Opportunities Workspace"
    {...evidenceAttributes({source: 'canonical opportunity store + Schwab movers', dataAsOf: canonicalPayload?.query_as_of || legacyPayload?.retrieved_at, freshness: 'CURRENT_QUERY'})}>
    <header className="qx-opportunities-header">
      <div>
        <span className="eyebrow">DISCOVERY / TRIAGE</span>
        <h1><Binoculars size={21}/> Opportunities</h1>
        <p>Scanner discovers. Trade decides. No client-generated canonical scores.</p>
      </div>
      <div className="qx-opportunity-scan">
        {fixtureEnabled
          ? <strong className="qx-preview-badge">TEST / PREVIEW DATA - NOT LIVE</strong>
          : <button type="button" onClick={runLiveScan} disabled={legacyLoading || !legacyRows.length || scanStatus.state === 'running'}>
              <RefreshCw className={scanStatus.state === 'running' ? 'spin' : ''} size={14}/>
              {scanStatus.state === 'running' ? `Evaluating ${scanStatus.completed}/${scanStatus.total}` : 'Evaluate live movers'}
            </button>}
        {!fixtureEnabled && scanStatus.message && <small role={scanStatus.state === 'error' ? 'alert' : 'status'}>{scanStatus.message}</small>}
      </div>
    </header>

    <section className="qx-opportunities-controls" aria-label="Opportunity filters">
      <div className="qx-opportunity-horizons" role="group" aria-label="Opportunity horizon">
        <span>Horizon</span>
        {horizons.map(value => <button key={value} type="button" aria-pressed={horizon === value} onClick={() => changeHorizon(value)}>{value}</button>)}
      </div>
      <label className="qx-opportunity-search"><span>Search</span><div><Search size={14}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Symbol, state, thesis"/></div></label>
      <label><span>Lifecycle</span><select value={stateFilter} onChange={event => setStateFilter(event.target.value)}><option>ACTIVE</option><option>ALL</option>{opportunityStates.map(state => <option key={state}>{state}</option>)}</select></label>
      <label><span>Direction</span><select value={directionFilter} onChange={event => setDirectionFilter(event.target.value)}>{directionOptions.map(value => <option key={value}>{value}</option>)}</select></label>
      <label><span>Sort</span><select value={sort} onChange={event => setSort(event.target.value)}>
        <option value="evaluation_desc">Evaluation newest</option>
        <option value="symbol">Symbol</option>
        <option value="state">Lifecycle state</option>
        <option value="return_desc">Legacy 1D return</option>
      </select></label>
    </section>

    <section className="qx-canonical-opportunities" aria-labelledby="canonical-opportunities-title">
      <div className="qx-opportunity-section-head">
        <div><span className="eyebrow">CANONICAL / CORE_V1</span><h2 id="canonical-opportunities-title">Canonical Opportunities</h2></div>
        <strong>{filteredCanonical.length} visible / {canonicalRows.length} loaded</strong>
      </div>
      <QXDataEvidence source={canonicalBars?.source || 'canonical opportunity store'} dataAsOf={canonicalBars?.dataAsOf || canonicalPayload?.query_as_of}
        retrievedAt={canonicalBars?.retrievedAt} freshness={canonicalBars?.freshness || 'CURRENT_QUERY'} label="Canonical field evidence"/>
      {canonicalLoading
        ? <p role="status" className="qx-opportunity-status"><RefreshCw className="spin" size={15}/> Loading canonical opportunitiesâ€¦</p>
        : canonicalError
          ? <div className="qx-opportunity-status" role="alert"><TriangleAlert size={16}/><span>{canonicalError}</span><button type="button" onClick={() => setAttempt(value => value + 1)}>Retry</button></div>
          : filteredCanonical.length === 0
          ? <UnavailableState
              title="NO CURRENT QUALIFYING OPPORTUNITIES"
              detail={fixtureEnabled ? 'No fixture observations match the selected canonical filters.' : canonicalEmptyDetail}
              action={!fixtureEnabled && stateFilter === 'ACTIVE' && !canonicalRows.length
                ? <button type="button" onClick={() => setStateFilter('ALL')}>Show all evaluations</button>
                : canonicalRows.length || canonicalFiltersApplied ? <button type="button" onClick={clearFilters}>Clear filters</button> : null}
            />
          : <div className="qx-opportunity-list" role="list">{filteredCanonical.map(row => <CanonicalOpportunityRow key={row.evaluationId || `${row.symbol}-${row.state}`} row={row} context={context}/>)}</div>}
      {!fixtureEnabled && canonicalPayload?.has_more && canonicalPayload.next_cursor && <div className="qx-opportunity-status" role="status">
        <span>{paginationError || 'More canonical opportunities are available.'}</span>
        <button type="button" onClick={loadMore} disabled={paginationLoading}>{paginationLoading ? 'Loading more…' : 'Load more'}</button>
      </div>}
    </section>

    <section className="qx-legacy-discovery" aria-labelledby="legacy-discovery-title">
      <div className="qx-opportunity-section-head">
        <div><span className="qx-legacy-source-badge">LEGACY SOURCE</span><h2 id="legacy-discovery-title">Verified Market Movement</h2></div>
        <p>Discovery context only. No canonical state, trigger, or tradeability is inferred.</p>
      </div>
      <QXDataEvidence source={legacyPayload?.source || 'schwab'} dataAsOf={legacyPayload?.market_as_of || legacyPayload?.retrieved_at}
        retrievedAt={legacyPayload?.retrieved_at} freshness="CURRENT_REQUEST" label="Mover field evidence"/>
      {legacyLoading
        ? <p role="status" className="qx-opportunity-status"><RefreshCw className="spin" size={15}/> Loading verified source…</p>
        : legacyError
          ? <div className="qx-opportunity-status" role="alert"><TriangleAlert size={16}/><span>{legacyError}</span><button type="button" onClick={() => setAttempt(value => value + 1)}>Retry</button></div>
          : legacyRows.length === 0
            ? <UnavailableState title="LEGACY DISCOVERY UNAVAILABLE" detail="The verified movers source returned no matching records."/>
            : <div className="qx-legacy-opportunity-list" role="list">{legacyRows.map(row => <LegacyDiscoveryRow key={row.symbol} row={row} context={context} horizon={horizon} timeframe={timeframe}/>)}</div>}
    </section>
  </article>;
}

function CanonicalOpportunityRow({row, context}) {
  const href = canonicalTradeHref(row, context);
  return <article className="qx-opportunity-row" role="listitem" data-source="canonical">
    <div className="qx-opportunity-symbol"><strong>{row.symbol}</strong><span>{row.horizon} · {display(row.timeframe)}</span></div>
    <Fact label="State"><span className={`qx-state qx-state-${row.state.toLowerCase()}`}>{row.state}</span></Fact>
    <Fact label="Direction" value={row.direction}/>
    <Fact label="Playbook / thesis" value={readable(row.playbook)}/>
    <Fact label="Market Driver" value={row.marketDriver}/>
    <Fact label="Trigger / risk" value={`${price(row.trigger)} / ${price(row.invalidation)}`} detail={row.triggerSource}/>
    <Fact label="Tradeability" value={display(row.tradeability)}/>
    <Fact label="Portfolio" value={display(row.portfolioRisk)}/>
    <Fact label="Coverage" value={percent(row.evidenceCoverage)} detail={row.coverageStatus}/>
    <Fact label="Freshness" value={timestamp(row.evaluationTimestamp)} detail={row.publicationState}/>
    <div className="qx-opportunity-actions">
      <details><summary>WHY</summary><OpportunityWhy row={row}/></details>
      <a href={href}>Open Trade <ArrowRight size={13}/></a>
    </div>
  </article>;
}

function LegacyDiscoveryRow({row, context, horizon, timeframe}) {
  const href = workspaceHref('trade', context, {
    symbol: row.symbol, etf: '', horizon, timeframe, evaluation_timestamp: '', evaluation_id: '',
  });
  return <article className="qx-legacy-opportunity-row" role="listitem" data-source="legacy">
    <div className="qx-opportunity-symbol"><strong>{row.symbol}</strong><span>{display(row.name)}</span></div>
    <span className="qx-legacy-source-badge">LEGACY SOURCE</span>
    <Fact label="Sector" value={display(row.sector)} detail={row.industry}/>
    <Fact label="1D move" value={percent(row.return1d)} detail={price(row.lastPrice)}/>
    <Fact label="SPY excess" value={percent(row.excess1d)} detail={row.benchmarkSource}/>
    <Fact label="Data as of" value={timestamp(row.asOf)} detail={display(row.source)}/>
    <a href={href}>Evaluate in Trade <ArrowRight size={13}/></a>
  </article>;
}

function OpportunityWhy({row}) {
  return <div className="qx-opportunity-why">
    <p><strong>Playbook / thesis:</strong> {readable(row.playbook)}</p>
    <p><strong>Market Driver:</strong> {display(row.marketDriver)}</p>
    <p><strong>Tradeability:</strong> {display(row.tradeability)}</p>
    <p><strong>Portfolio:</strong> {display(row.portfolioRisk)}</p>
    <p><strong>Freshness:</strong> {timestamp(row.evaluationTimestamp)} / {display(row.publicationState)}</p>
    <p><strong>Provenance:</strong> {row.dependencies.length ? row.dependencies.map(item => `${item.name}: ${item.freshness}`).join(', ') : 'UNAVAILABLE'}</p>
    <p><strong>Evaluation:</strong> {display(row.evaluationId)}</p>
    <p><strong>Pipeline:</strong> {row.pipelineVersion}</p>
    <p><strong>Options:</strong> {display(row.optionsSuitability)}</p>
    <p><strong>Reasons:</strong> {row.reasonCodes.length ? row.reasonCodes.join(', ') : 'UNAVAILABLE'}</p>
  </div>;
}

function Fact({label, value, detail, children}) {
  return <div className="qx-opportunity-fact"><span>{label}</span>{children || <strong>{display(value)}</strong>}{detail && <small>{display(detail)}</small>}</div>;
}

function UnavailableState({title, detail, action = null}) {
  return <div className="qx-opportunity-empty" role="status"><TriangleAlert size={18}/><div><strong>{title}</strong><p>{detail}</p></div>{action}</div>;
}

function canonicalTradeHref(row, context) {
  const href = new URL(workspaceHref('trade', context, tradeHandoffUpdates(row)));
  if (row.fixtureState) href.searchParams.set('fixture_state', row.fixtureState);
  return `${href.pathname}${href.search}`;
}

function mergeOpportunityPages(current, nextPage) {
  const items = [...(current?.items || []), ...(nextPage?.items || [])];
  const seen = new Set();
  return {
    ...nextPage,
    items: items.filter(item => {
      const key = item.evaluation_id || `${item.symbol}:${item.timeframe}:${item.evaluation_timestamp}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }),
  };
}

function display(value) {
  return value == null || value === '' ? 'UNAVAILABLE' : String(value);
}

function readable(value) {
  return display(value).replaceAll('_', ' ');
}

function price(value) {
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : 'UNAVAILABLE';
}

function percent(value) {
  return Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%` : 'UNAVAILABLE';
}

function timestamp(value) {
  if (!value) return 'UNAVAILABLE';
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString() : String(value);
}
