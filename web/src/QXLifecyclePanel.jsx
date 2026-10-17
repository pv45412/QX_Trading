import React, {Profiler, memo, useMemo} from 'react';
import {Activity, AlertTriangle, CheckCircle2, RefreshCw} from 'lucide-react';
import {adaptQxV2Evaluation, lifecyclePath} from './qx-v2-adapter';

const stateDescriptions = {
  BLOCKED: 'Evaluation cannot proceed with the available canonical evidence.',
  NO_SETUP: 'No qualifying setup is present. Monitoring continues.',
  WATCH: 'Potential setup developing.',
  ARMED: 'Setup complete — waiting for trigger.',
  TRIGGERED: 'Trigger confirmed.',
  NOT_TRADEABLE: 'Trigger occurred, but tradeability gates did not pass.',
  TRADEABLE: 'Participation and tradeability gates passed.',
  OPTIONS_NOT_SUITABLE: 'No suitable defined-risk options expression is available.',
  OPTIONS_SUITABLE: 'Defined-risk options expression available.',
  PORTFOLIO_VETOED: 'Portfolio risk gate vetoed the candidate.',
  PORTFOLIO_APPROVED: 'Portfolio risk gate passed.',
  EXPIRED: 'The setup expired before completing the lifecycle.',
  UNAVAILABLE: 'Canonical lifecycle state is unavailable.',
};

const evidenceStages = [
  ['Structure', 'STRUCTURE'],
  ['Regime', 'REGIME'],
  ['Direction', 'DIRECTION'],
  ['Playbook', 'PLAYBOOK'],
  ['Trigger', 'TRIGGER'],
  ['Tradeability', 'TRADEABILITY'],
  ['Options', 'OPTIONS'],
  ['Portfolio', 'PORTFOLIO'],
  ['Pipeline', 'PIPELINE'],
];

function QXLifecyclePanel({result, loading, error, onRetry}) {
  const view = useMemo(() => adaptQxV2Evaluation(result), [result]);
  return (
    <Profiler id="QXLifecyclePanel" onRender={recordRender}>
      <section className="qx-lifecycle-panel" aria-label="Canonical QX lifecycle">
        <div className="qx-lifecycle-heading">
          <div>
            <span className="eyebrow">CANONICAL V2 / CORE_V1</span>
            <h3><Activity size={16}/> Deterministic Lifecycle</h3>
          </div>
          {loading && <span role="status"><RefreshCw size={13} className="spin"/> Evaluating</span>}
        </div>
        {error && (
          <div className="qx-lifecycle-error" role="alert">
            <AlertTriangle size={15}/><span>{error}</span>
            <button type="button" onClick={onRetry}>Retry V2</button>
          </div>
        )}
        {!loading && !error && !view && <p role="status">Canonical evaluation unavailable.</p>}
        {view && <LifecycleContent view={view}/>} 
      </section>
    </Profiler>
  );
}

export default memo(QXLifecyclePanel);

function LifecycleContent({view}) {
  const reachedIndex = lifecyclePath.indexOf(view.state);
  return <>
    <div className="qx-lifecycle-identity" aria-label="Canonical evaluation identity">
      <Metric label="Symbol" value={display(view.symbol)}/>
      <Metric label="Timeframe" value={display(view.timeframe)}/>
      <Metric label="Evaluation timestamp" value={display(view.evaluationTimestamp)}/>
      <Metric label="Evaluation ID" value={display(view.evaluationId)}/>
      <Metric label="Pipeline" value={display(view.pipelineVersion)}/>
    </div>
    <div className="qx-lifecycle-current">
      <div><span>Current lifecycle state</span><strong className={`qx-state qx-state-${view.state.toLowerCase()}`}>{view.state}</strong></div>
      <p>{stateDescriptions[view.state] || stateDescriptions.UNAVAILABLE}</p>
      <small>{view.publicationState}</small>
    </div>
    <ol className="qx-lifecycle-rail" aria-label="Lifecycle progression">
      {lifecyclePath.map((state, index) => (
        <li key={state} className={state === view.state ? 'current' : reachedIndex >= index ? 'reached' : ''}>
          <CheckCircle2 size={13}/><span>{state}</span>
        </li>
      ))}
    </ol>
    {view.stateCategory === 'terminal' && (
      <div className="qx-lifecycle-branch" role="status">
        <strong>{view.state}</strong><span>{stateDescriptions[view.state]}</span>
      </div>
    )}
    <div className="qx-lifecycle-sections">
      <SummaryCard title="Structure" className="qx-card-structure">
        <Metric label="Bias" value={display(view.structureSummary.bias)}/>
        <Metric label="Score" value={formatNumber(view.structureSummary.score)}/>
        <Metric label="Latest BOS" value={display(view.structureSummary.latestBos)}/>
        <Metric label="Latest CHoCH" value={display(view.structureSummary.latestChoch)}/>
        <Metric label="Event timestamp" value={display(view.structureSummary.latestEventTimestamp)}/>
        <Metric label="Knowledge timestamp" value={display(view.structureSummary.latestKnowledgeTimestamp)}/>
        <Metric label="Protected high" value={formatPrice(view.structureSummary.protectedHigh)}/>
        <Metric label="Protected low" value={formatPrice(view.structureSummary.protectedLow)}/>
      </SummaryCard>
      <SummaryCard title="Market Regime" className="qx-card-regime">
        <Metric label="Trend" value={display(view.marketRegime.trend)}/>
        <Metric label="Volatility" value={display(view.marketRegime.volatility)}/>
        <Metric label="Gamma" value={display(view.marketRegime.gamma)}/>
        <Metric label="Session" value={display(view.marketRegime.session)}/>
      </SummaryCard>
      <SummaryCard title="Direction & Playbook" className="qx-card-direction">
        <Metric label="Direction" value={display(view.directionLabel)}/>
        <Metric label="Score" value={formatNumber(view.directionScore)}/>
        <Metric label="Evidence coverage" value={formatPercent(view.evidenceCoverage)}/>
        <Metric label="Coverage status" value={display(view.coverageStatus)}/>
        <Metric label="Primary playbook" value={display(view.playbook)}/>
        <Metric label="Playbook state" value={display(view.playbookState)}/>
      </SummaryCard>
      <SummaryCard title="Trigger & Invalidation" className="qx-card-trigger">
        <Metric label="Trigger level" value={formatPrice(view.trigger)}/>
        <Metric label="Trigger condition" value={display(view.triggerCondition)}/>
        <Metric label="Confirmation" value={view.triggerSource}/>
        <Metric label="Event timestamp" value={display(view.triggerEventTimestamp)}/>
        <Metric label="Knowledge timestamp" value={display(view.triggerKnowledgeTimestamp)}/>
        <Metric label="Invalidation level" value={formatPrice(view.invalidation)}/>
        <Metric label="Invalidation condition" value={display(view.invalidationCondition)}/>
      </SummaryCard>
      <SummaryCard title="Tradeability" className="qx-card-tradeability">
        <Metric label="Status" value={display(view.tradeabilitySummary.state)}/>
        <Metric label="Participation" value={formatNumber(view.tradeabilitySummary.participationScore)}/>
        <Metric label="Participation coverage" value={formatPercent(view.tradeabilitySummary.participationCoverage)}/>
        <Metric label="Structural R:R" value={formatRatio(view.tradeabilitySummary.structuralRiskReward)}/>
        <Metric label="Observed entry" value={formatPrice(view.tradeabilitySummary.observedEntryReference)}/>
        <Metric label="Best target" value={formatPrice(view.tradeabilitySummary.targetCandidates[0])}/>
      </SummaryCard>
      <SummaryCard title="Options Expression" className="qx-card-options">
        <Metric label="Suitability" value={display(view.optionsSummary.state)}/>
        <Metric label="Primary strategy" value={display(view.optionsSummary.strategyType)}/>
        <Metric label="Expiration" value={display(view.optionsSummary.expiration)}/>
        <Metric label="Candidates" value={displayNumber(view.optionsSummary.candidateCount)}/>
        <Metric label="Max loss" value={formatPrice(view.optionsSummary.maxLoss)}/>
        <Metric label="Max profit" value={formatPrice(view.optionsSummary.maxProfit)}/>
        <Metric label="Data as of" value={display(view.optionsSummary.dataAsOf)}/>
      </SummaryCard>
      <SummaryCard title="Portfolio Risk" className="qx-card-portfolio">
        <Metric label="Decision" value={display(view.portfolioSummary.state)}/>
        <Metric label="Binding constraint" value={display(view.portfolioSummary.bindingConstraint)}/>
        <Metric label="Approved contract cap" value={displayNumber(view.portfolioSummary.approvedContractsCap)}/>
        <Metric label="Snapshot evidence" value={display(view.portfolioSummary.evidenceStatus)}/>
        <Metric label="Data as of" value={display(view.portfolioSummary.dataAsOf)}/>
      </SummaryCard>
    </div>
    <StageAvailability stages={view.stageAvailability}/>
    <DataFreshness dependencies={view.dependencies}/>
    <WhyEvidence view={view}/>
  </>;
}

function SummaryCard({title, className = '', children}) {
  return <section className={`qx-lifecycle-card ${className}`}><h4>{title}</h4><dl>{children}</dl></section>;
}

function StageAvailability({stages}) {
  return <section className="qx-stage-availability">
    <h4>Stage availability</h4>
    <ul>{stages.map(stage => <li key={stage.key} data-status={stage.status}>
      <span>{stage.label}</span><strong>{stage.status}</strong>
      <small>{stage.latencyMs == null ? 'Latency unavailable' : `${stage.latencyMs.toFixed(2)} ms`}</small>
    </li>)}</ul>
  </section>;
}

function DataFreshness({dependencies}) {
  return <section className="qx-stage-availability">
    <h4>Data freshness & provenance</h4>
    {dependencies.length ? <ul>{dependencies.map(dependency => <li key={dependency.name} data-status={dependency.available ? 'AVAILABLE' : 'UNAVAILABLE'}>
      <span>{dependency.name}</span><strong>{dependency.freshness}</strong>
      <small>{dependency.source} / {dependency.syncStatus} / {dependency.publicationState}</small>
      <small>As of: {display(dependency.dataAsOf)}</small>
      {dependency.reason && <small>{dependency.reason}</small>}
    </li>)}</ul> : <p>Provider provenance unavailable.</p>}
  </section>;
}

function WhyEvidence({view}) {
  return <details className="qx-lifecycle-why">
    <summary>WHY?</summary>
    <section className="qx-reason-codes"><h4>Reason codes</h4>
      {view.reasons.length ? <ul>{view.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul> : <p>No reason codes supplied.</p>}
    </section>
    <div className="qx-evidence-groups">
      {evidenceStages.map(([stage, label]) => {
        const items = view.evidence.filter(item => item.stage === stage);
        if (!items.length) return null;
        return <section key={stage} className="qx-evidence-stage" aria-label={`${label} evidence`}>
          <h4>{label}</h4>
          <ul>{items.map((item, index) => <EvidenceItem key={item.ruleIdentity || `${item.stage}-${item.key}-${index}`} item={item}/>)}</ul>
        </section>;
      })}
    </div>
    {!view.evidence.length && <p>Evidence unavailable for this state.</p>}
  </details>;
}

function EvidenceItem({item}) {
  if (item.type !== 'RULE_RESULT') {
    return <li className="qx-evidence-item"><strong>{item.key}</strong><span>{item.value}</span></li>;
  }
  const rule = item.ruleResult;
  return <li className="qx-evidence-item qx-rule-evidence">
    <div className="qx-rule-heading">
      <strong>{display(rule.rule_id)}</strong>
      <span data-result={rule.passed === true ? 'PASS' : rule.passed === false ? 'FAIL' : 'UNKNOWN'}>
        {rule.passed === true ? 'PASS' : rule.passed === false ? 'FAIL' : 'UNAVAILABLE'}
      </span>
    </div>
    <dl>
      <Metric label="Rule version" value={evidenceValue(rule.rule_version)}/>
      <Metric label="Category" value={evidenceValue(rule.category)}/>
      <Metric label="Required" value={evidenceValue(rule.required_value)}/>
      <Metric label="Observed" value={evidenceValue(rule.observed_value)}/>
      <Metric label="Severity" value={evidenceValue(rule.severity)}/>
      <Metric label="Hard gate" value={evidenceValue(rule.hard_gate)}/>
      <Metric label="Weight" value={evidenceValue(rule.weight)}/>
      <Metric label="Contribution" value={evidenceValue(rule.contribution)}/>
      <Metric label="Provenance" value={evidenceValue(rule.data_source)}/>
      <Metric label="Event timestamp" value={evidenceValue(rule.event_timestamp)}/>
      <Metric label="Knowledge timestamp" value={evidenceValue(rule.knowledge_timestamp)}/>
      <Metric label="Detail" value={evidenceValue(rule.detail)}/>
    </dl>
  </li>;
}

function Metric({label, value}) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function display(value) {
  return value == null || value === '' ? 'UNAVAILABLE' : String(value);
}

function displayNumber(value) {
  return Number.isFinite(value) ? String(value) : 'UNAVAILABLE';
}

function formatNumber(value) {
  return Number.isFinite(value) ? value.toFixed(1) : 'UNAVAILABLE';
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : 'UNAVAILABLE';
}

function formatPrice(value) {
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : 'UNAVAILABLE';
}

function formatRatio(value) {
  return Number.isFinite(value) ? `${value.toFixed(2)}R` : 'UNAVAILABLE';
}

function evidenceValue(value) {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  if (value === '') return '""';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function recordRender(_id, phase, actualDuration) {
  globalThis.__QX_PERFORMANCE__ = globalThis.__QX_PERFORMANCE__ || {};
  const renders = globalThis.__QX_PERFORMANCE__.lifecycleRenders || [];
  renders.push({phase, actualDuration});
  globalThis.__QX_PERFORMANCE__.lifecycleRenders = renders;
}
