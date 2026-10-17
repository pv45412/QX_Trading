import React, {useEffect, useMemo, useState} from 'react';
import {AlertTriangle, ArrowRight, CheckCircle2, Crosshair, Info, ShieldCheck, TrendingDown, TrendingUp} from 'lucide-react';
import QXLifecyclePanel from './QXLifecyclePanel';
import QXMarketDriverPanel from './QXMarketDriverPanel';
import {updateWorkspaceContext, workspaceHref} from './workspace-context';
import {isQxTradeFixtureEnabled} from './qx-v2-feature';
import {createQxV2PreviewFixture, previewStates} from './qx-v2-fixtures';
import {buildTradeWorkspaceView, readable} from './qx-trade-workspace-model';
import useQxV2Evaluation from './useQxV2Evaluation';
import QXDataEvidence, {evidenceAttributes} from './QXDataEvidence';

const horizons = ['DAY', 'SWING', 'INVEST'];
const timeframes = ['1m', '5m', '15m', '1h', '1d'];
const setupByHorizon = {DAY: '5m', SWING: '1h', INVEST: '1d'};

export default function QXTradeWorkspace({context}) {
  const symbol = context.symbol || context.etf || 'SPY';
  const horizon = context.horizon || 'DAY';
  const timeframe = context.timeframe || '5m';
  const [symbolDraft, setSymbolDraft] = useState(symbol);
  const query = new URLSearchParams(location.search);
  const requestedFixture = query.get('fixture_state');
  const fixtureEnabled = isQxTradeFixtureEnabled() && previewStates.includes(requestedFixture);
  const fixtureResult = useMemo(() => {
    if (!fixtureEnabled) return null;
    return {
      ...createQxV2PreviewFixture(requestedFixture, symbol),
      timeframe,
      evaluation_id: context.evaluation_id ?? null,
    };
  }, [context.evaluation_id, fixtureEnabled, requestedFixture, symbol, timeframe]);
  const live = useQxV2Evaluation(symbol, !fixtureEnabled, {
    timeframe,
    evaluationTimestamp: context.evaluation_timestamp || null,
    evaluationId: context.evaluation_id || null,
  });
  const result = fixtureResult || live.data;
  const visibleResult = result?.symbol?.toUpperCase() === symbol.toUpperCase() ? result : null;
  const workspace = useMemo(() => buildTradeWorkspaceView(visibleResult), [visibleResult]);
  const portfolioHref = workspace ? linkedPortfolioHref(workspace, context, requestedFixture) : null;

  useEffect(() => setSymbolDraft(symbol), [symbol]);

  const changeContext = updates => updateWorkspaceContext(updates);
  const submitSymbol = event => {
    event.preventDefault();
    const nextSymbol = symbolDraft.trim().toUpperCase();
    if (/^[A-Z0-9^/][A-Z0-9.^=/\-]{0,19}$/.test(nextSymbol)) changeContext({symbol: nextSymbol});
  };

  const canon = workspace?.canonical;
  const barsEvidence = canon?.dependencies.find(dependency => dependency.name === 'bars') || null;
  const isBlocked = canon?.publicationState === 'BLOCKED' || canon?.state === 'BLOCKED';

  return <article className="qx-trade-workspace" aria-label="Canonical Trade Workspace"
    {...evidenceAttributes({source: barsEvidence?.source || 'canonical core_v1', dataAsOf: barsEvidence?.dataAsOf || canon?.evaluationTimestamp, freshness: barsEvidence?.freshness || canon?.publicationState})}>
    <header className="qx-trade-header">
      <div>
        <span className="eyebrow">CANONICAL V2 / CORE_V1</span>
        <h1><Crosshair size={21}/> Trade Workspace</h1>
        <p>One symbol. One canonical decision chain. No execution.</p>
      </div>
      <div className="qx-trade-header-actions">
        {fixtureEnabled && <strong className="qx-preview-badge">TEST / PREVIEW DATA - NOT LIVE</strong>}
        {portfolioHref && <a href={portfolioHref}>View Portfolio Impact <ArrowRight size={13}/></a>}
      </div>
    </header>

    {/* Controls */}
    <section className="qx-trade-controls" aria-label="Trade Workspace context">
      <form onSubmit={submitSymbol}>
        <label>Symbol<input aria-label="Trade symbol" value={symbolDraft} onChange={event => setSymbolDraft(event.target.value)}/></label>
        <button type="submit">Evaluate</button>
      </form>
      <div className="qx-trade-control-group" role="group" aria-label="Trading horizon">
        <span>Horizon</span>
        {horizons.map(value => <button key={value} type="button" aria-pressed={horizon === value} onClick={() => changeContext({horizon: value, timeframe: setupByHorizon[value]})}>{value}</button>)}
      </div>
      <label>Timeframe<select aria-label="Trade timeframe" value={timeframe} onChange={event => changeContext({timeframe: event.target.value, horizon: horizonForTimeframe(event.target.value)})}>
        {timeframes.map(value => <option key={value}>{value}</option>)}
      </select></label>
    </section>

    {fixtureEnabled && <div className="qx-trade-fixture-controls" role="group" aria-label="Trade fixture state">
      {previewStates.map(state => <a key={state} className={state === requestedFixture ? 'active' : ''} href={fixtureHref(state)}>{state}</a>)}
    </div>}

    {/* Blocked / error state */}
    {!workspace && (live.loading || live.error || fixtureEnabled) && (
      <QXLifecyclePanel result={visibleResult} loading={!fixtureEnabled && live.loading} error={fixtureEnabled ? '' : live.error} onRetry={live.retry}/>
    )}

    {workspace && <>
      {/* ─── HERO: Above-the-fold decision summary ─── */}
      <section className="qx-trade-hero" aria-label="Primary decision summary">
        <div className="qx-trade-hero-identity">
          <div className="qx-trade-hero-symbol">
            <strong>{canon.symbol}</strong>
            <span>{horizon} · {canon.timeframe || timeframe}</span>
          </div>
          <span className={`qx-state qx-state-${canon.state.toLowerCase()} qx-trade-hero-state`}>
            {canon.state}
          </span>
        </div>
        <QXDataEvidence source={barsEvidence?.source || 'canonical core_v1'} dataAsOf={barsEvidence?.dataAsOf || canon.evaluationTimestamp}
          freshness={barsEvidence?.freshness || canon.publicationState} label="Decision field evidence"/>

        {isBlocked && workspace.blockedReason && (
          <div className="qx-trade-blocked-reason" role="alert">
            <AlertTriangle size={15}/>
            <span>{workspace.blockedReason}</span>
          </div>
        )}

        {!isBlocked && (
          <div className="qx-trade-hero-facts">
            <HeroFact label="Direction" value={canon.directionLabel} emphasis/>
            <HeroFact label="Regime" value={canon.marketRegime.trend}/>
            <HeroFact label="Playbook" value={readable(canon.playbook)}/>
            <HeroFact label="Trigger" value={price(canon.trigger)}/>
            <HeroFact label="Invalidation" value={price(canon.invalidation)}/>
            <HeroFact label="Target" value={price(workspace.target)}/>
            <HeroFact label="R:R" value={ratio(canon.tradeabilitySummary.structuralRiskReward)}/>
            <HeroFact label="Tradeability" value={canon.tradeabilitySummary.state}/>
            <HeroFact label="Options" value={canon.optionsSummary.state}/>
            <HeroFact label="Portfolio" value={canon.portfolioSummary.state}/>
          </div>
        )}

        {workspace.freshnessWarning && (
          <div className="qx-trade-warning" role="status">
            <AlertTriangle size={15}/>
            <span>{workspace.freshnessWarning}</span>
          </div>
        )}

        {workspace.failedGateSummary && !isBlocked && (
          <div className="qx-trade-gate-reason">
            <Info size={13}/><span>{workspace.failedGateSummary}</span>
          </div>
        )}
      </section>

      {/* ─── DECISION QUESTIONS ─── */}
      <section className="qx-decision-summary" aria-labelledby="decision-summary-title">
        <div className="qx-decision-title">
          <span className="eyebrow">DECISION SUMMARY</span>
        </div>
        <QuestionCard question="What is happening?" answer={workspace.whatIsHappening}/>
        <QuestionCard question="What does QX see?" answer={workspace.whatQxSees}/>
        <QuestionCard question="What are we waiting for?" answer={workspace.waitingFor}/>
        <QuestionCard question="Where is QX wrong?" answer={workspace.whereWrong}/>
        <QuestionCard question="Is there a trade?" answer={workspace.isThereATrade}/>
      </section>

      {/* ─── MARKET DRIVER (backend data) ─── */}
      <section className="qx-trade-panel-section" aria-label="Market Driver">
        <div className="qx-trade-panel-heading">
          <span className="eyebrow">MARKET DRIVER</span>
          <small>Backend deterministic attribution — no frontend inference</small>
        </div>
        <QXMarketDriverPanel
          driver={canon.marketDriver}
          symbol={canon.symbol}
          compact={false}
          blockedReason={isBlocked ? (canon.reasons[0] ?? null) : null}
        />
      </section>

      {/* ─── MULTI-TIMEFRAME / HTF CONTEXT (BE2) ─── */}
      <section className="qx-trade-panel-section" aria-label="Multi-timeframe context">
        <div className="qx-trade-panel-heading">
          <span className="eyebrow">MULTI-TIMEFRAME CONTEXT</span>
          <small>BE2 Option B — HTF is evidence, not a lifecycle veto</small>
        </div>
        <HTFPanel
          htfContext={workspace.htfContext}
          setupTimeframe={canon.timeframe || timeframe}
          htfTimeframe={canon.htfTimeframe}
          macroTimeframe={canon.macroTimeframe}
        />
      </section>

      {/* ─── STRUCTURE SUMMARY ─── */}
      <section className="qx-trade-panel-section" aria-label="Structure summary">
        <div className="qx-trade-panel-heading">
          <span className="eyebrow">STRUCTURE</span>
        </div>
        <StructureSummary structure={canon.structureSummary}/>
      </section>

      {/* ─── FULL CANONICAL LIFECYCLE ─── */}
      <QXLifecyclePanel result={visibleResult} loading={!fixtureEnabled && live.loading} error={fixtureEnabled ? '' : live.error} onRetry={live.retry}/>

      {/* ─── EXECUTION READINESS ─── */}
      <section className="qx-execution-readiness" aria-label="Execution Readiness">
        <div><ShieldCheck size={18}/><span className="eyebrow">EXECUTION READINESS</span></div>
        <strong>NOT ENABLED</strong>
        <p>Phase 11 is not approved. Portfolio approval is not an order.</p>
      </section>
    </>}

    {/* Loading / error when no workspace built yet */}
    {!workspace && !live.loading && !live.error && !fixtureEnabled && (
      <QXLifecyclePanel result={null} loading={false} error="" onRetry={live.retry}/>
    )}
  </article>;
}

/* ─── Sub-components ─── */

function HeroFact({label, value, emphasis = false}) {
  const display = value == null || value === '' ? 'UNAVAILABLE' : String(value);
  return (
    <div className={`qx-hero-fact${emphasis ? ' qx-hero-fact-emphasis' : ''}`}>
      <span>{label}</span>
      <strong>{display}</strong>
    </div>
  );
}

function HTFPanel({htfContext, setupTimeframe, htfTimeframe, macroTimeframe}) {

  return (
    <div className="qx-htf-panel">
      <div className="qx-htf-timeframes">
        <div className="qx-htf-tf-item">
          <span>Setup / Execution</span>
          <strong>{timeframeLabel(setupTimeframe)}</strong>
        </div>
        <div className="qx-htf-tf-item qx-htf-tf-primary">
          <span>HTF (Factor #7)</span>
          <strong>{timeframeLabel(htfTimeframe)}</strong>
        </div>
        <div className="qx-htf-tf-item">
          <span>Macro</span>
          <strong>{timeframeLabel(macroTimeframe)}</strong>
        </div>
      </div>

      {htfContext ? (
        <div className="qx-htf-factor">
          <div className={`qx-htf-direction qx-htf-${htfContext.direction?.toLowerCase()}`}>
            {htfContext.direction === 'ALIGNED' && <CheckCircle2 size={13}/>}
            {htfContext.direction === 'OPPOSING' && <AlertTriangle size={13}/>}
            <strong>{htfContext.direction ?? 'UNAVAILABLE'}</strong>
          </div>
          <dl className="qx-htf-metrics">
            <div>
              <dt>Score contribution</dt>
              <dd>{scoreContribution(htfContext.contribution)}</dd>
            </div>
            <div>
              <dt>Availability</dt>
              <dd>{htfContext.availability ?? 'UNAVAILABLE'}</dd>
            </div>
          </dl>
          {htfContext.detail && <p className="qx-htf-detail">{htfContext.detail}</p>}
          <small className="qx-htf-note">HTF adds weighted evidence — it does not veto ARMED or TRIGGERED states.</small>
        </div>
      ) : (
        <div className="qx-htf-unavailable">
          <Info size={13}/>
          <span>HTF factor not present in direction evidence. This occurs when direction stage is blocked or unavailable.</span>
        </div>
      )}
    </div>
  );
}

function StructureSummary({structure}) {
  if (!structure) {
    return <div className="qx-structure-unavailable"><span>Structure data unavailable.</span></div>;
  }
  return (
    <div className="qx-structure-summary">
      <dl className="qx-structure-facts">
        <div>
          <dt>Bias</dt>
          <dd>{display(structure.bias)}</dd>
        </div>
        <div>
          <dt>Latest event</dt>
          <dd>{display(structure.latestEventType)}</dd>
        </div>
        <div>
          <dt>Latest BOS</dt>
          <dd>{display(structure.latestBos)}</dd>
        </div>
        <div>
          <dt>Latest CHoCH</dt>
          <dd>{display(structure.latestChoch)}</dd>
        </div>
        <div>
          <dt>Protected high</dt>
          <dd>{priceOrNull(structure.protectedHigh)}</dd>
        </div>
        <div>
          <dt>Protected low</dt>
          <dd>{priceOrNull(structure.protectedLow)}</dd>
        </div>
      </dl>
      {structure.latestKnowledgeTimestamp && (
        <small className="qx-structure-knowledge">Knowledge as of {shortTime(structure.latestKnowledgeTimestamp)}</small>
      )}
    </div>
  );
}

function QuestionCard({question, answer}) {
  return <section className="qx-question-card"><h3>{question}</h3><p>{answer}</p><ArrowRight size={14}/></section>;
}

/* ─── Helpers ─── */

function horizonForTimeframe(timeframe) {
  if (timeframe === '1d') return 'INVEST';
  if (timeframe === '1h') return 'SWING';
  return 'DAY';
}

function timeframeLabel(timeframe) {
  if (timeframe === '1d') return 'Daily';
  if (timeframe === '1w') return 'Weekly';
  return timeframe || 'UNAVAILABLE';
}

function scoreContribution(value) {
  if (!Number.isFinite(value)) return 'UNAVAILABLE';
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)} pts`;
}

function display(value) {
  return value == null || value === '' ? 'UNAVAILABLE' : String(value);
}

function price(value) {
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : 'UNAVAILABLE';
}

function priceOrNull(value) {
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : 'UNAVAILABLE';
}

function ratio(value) {
  return Number.isFinite(value) ? `${value.toFixed(2)}R` : 'UNAVAILABLE';
}

function shortTime(value) {
  if (!value) return 'UNAVAILABLE';
  try {
    return new Date(value).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
  } catch {
    return String(value);
  }
}

function fixtureHref(state) {
  const url = new URL(location.href);
  url.searchParams.set('fixture_state', state);
  return `${url.pathname}${url.search}`;
}

function linkedPortfolioHref(workspace, context, fixtureState) {
  const href = new URL(workspaceHref('portfolio', context, {
    symbol: workspace.canonical.symbol,
    horizon: context.horizon || 'DAY',
    timeframe: workspace.canonical.timeframe || context.timeframe || '5m',
    evaluation_timestamp: workspace.canonical.evaluationTimestamp || '',
    evaluation_id: workspace.canonical.evaluationId || '',
  }));
  if (fixtureState === 'PORTFOLIO_APPROVED') href.searchParams.set('portfolio_state', 'approved');
  if (fixtureState === 'PORTFOLIO_VETOED') href.searchParams.set('portfolio_state', 'vetoed');
  return `${href.pathname}${href.search}`;
}
