import {adaptQxV2Evaluation} from './qx-v2-adapter.js';

const nextActions = {
  BLOCKED: 'Inspect the blocked dependency or data-health exception. Canonical evaluation cannot progress.',
  NO_SETUP: 'No qualifying setup is present. Continue monitoring or return to Opportunities.',
  WATCH: 'Setup evidence is developing. Wait for the playbook to become armed.',
  ARMED: 'Setup formed. Wait for the canonical trigger condition.',
  TRIGGERED: 'Trigger confirmed. Tradeability is the next required gate.',
  NOT_TRADEABLE: 'Tradeability failed. Review the failed gate without discarding valid trigger evidence.',
  TRADEABLE: 'Underlying tradeability passed. Options suitability and portfolio risk are downstream.',
  OPTIONS_NOT_SUITABLE: 'No suitable canonical options expression is available for this setup.',
  OPTIONS_SUITABLE: 'A canonical options expression is available. Portfolio risk approval remains.',
  PORTFOLIO_VETOED: 'Portfolio risk vetoed the candidate. Review the binding constraint.',
  PORTFOLIO_APPROVED: 'Portfolio risk passed. Execution remains disabled (Phase 11 not approved).',
  EXPIRED: 'The setup expired. Return to Opportunities or inspect historical evidence.',
};

const tradeStatements = {
  BLOCKED: 'No. Required canonical evidence is blocked.',
  NO_SETUP: 'No. There is no qualifying setup.',
  WATCH: 'No. The setup is still developing.',
  ARMED: 'Not yet. The canonical trigger has not confirmed.',
  TRIGGERED: 'Not yet. Tradeability gates remain.',
  NOT_TRADEABLE: 'No. Tradeability gates did not pass.',
  TRADEABLE: 'Underlying tradeability passed; downstream risk checks remain.',
  OPTIONS_NOT_SUITABLE: 'No canonical options expression is suitable.',
  OPTIONS_SUITABLE: 'Options suitable; portfolio approval remains.',
  PORTFOLIO_VETOED: 'No. Portfolio risk vetoed the candidate.',
  PORTFOLIO_APPROVED: 'Risk approved. Execution is not enabled.',
  EXPIRED: 'No. The setup has expired.',
};

/** Human-readable labels for reason codes shown in the primary view. */
const reasonLabels = {
  NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP: 'Outside market hours — no current bar data.',
  STALE_BARS: 'Bar data is stale — pipeline is waiting for fresh market data.',
  PIPELINE_BLOCKED: 'Canonical pipeline blocked. Check System for data health.',
  INSUFFICIENT_BARS: 'Insufficient bar history for evaluation.',
  SETUP_INVALIDATED: 'Setup was invalidated before triggering.',
  TRIGGER_EXPIRED: 'Trigger window expired without confirmation.',
  NO_TRADEABLE_PLAYBOOK: 'No tradeable playbook matched the current structure.',
  RR_BELOW_MINIMUM: 'Structural R:R is below the minimum threshold.',
  PARTICIPATION_BELOW_MINIMUM: 'Market participation is too low to support entry.',
  OPTIONS_CHAIN_STALE: 'Options chain data is stale.',
};

export function buildTradeWorkspaceView(payload) {
  const canonical = adaptQxV2Evaluation(payload);
  if (!canonical) return null;
  const materialDependencies = canonical.dependencies.filter(dependency => (
    !dependency.available
    || dependency.publicationState === 'BLOCKED'
    || dependency.syncStatus === 'PARTIAL'
    || ['STALE', 'STALE_BLOCKED', 'INVALID', 'UNAVAILABLE'].includes(dependency.freshness)
  ));
  const target = canonical.tradeabilitySummary.targetCandidates[0] ?? null;
  const blockedReason = humanizeBlockedReason(canonical);
  return {
    canonical,
    whatIsHappening: marketContext(canonical),
    whatQxSees: qxView(canonical),
    waitingFor: nextActions[canonical.state] || 'Canonical next action is unavailable.',
    whereWrong: invalidationView(canonical),
    isThereATrade: tradeStatements[canonical.state] || 'Trade status is unavailable.',
    target,
    blockedReason,
    freshnessWarning: materialDependencies.length
      ? `${materialDependencies.length} canonical data ${materialDependencies.length === 1 ? 'dependency requires' : 'dependencies require'} attention.`
      : null,
    failedGateSummary: firstReason(canonical),
    htfContext: buildHtfContext(canonical),
  };
}

function marketContext(view) {
  const driverPart = view.marketDriver?.primary_driver
    ? `${readable(view.marketDriver.primary_driver.driver_id)} (${readable(view.marketDriver.primary_driver.strength)}).`
    : 'Market driver unavailable.';
  return [
    driverPart,
    `Trend ${readable(view.marketRegime.trend)}, volatility ${readable(view.marketRegime.volatility)}, session ${readable(view.marketRegime.session)}.`,
  ].join(' ');
}

function qxView(view) {
  return `${readable(view.state)}: ${readable(view.directionLabel)} direction, ${readable(view.structureSummary.bias)} structure, ${readable(view.playbook)} playbook.`;
}

function invalidationView(view) {
  if (!Number.isFinite(view.invalidation)) return 'Invalidation is unavailable.';
  const condition = view.invalidationCondition ? ` (${readable(view.invalidationCondition)})` : '';
  return `$${view.invalidation.toFixed(2)}${condition}`;
}

function firstReason(view) {
  let stageReasons = view.reasons;
  if (view.state.startsWith('PORTFOLIO_')) stageReasons = view.portfolioSummary.reasonCodes;
  else if (view.state.startsWith('OPTIONS_')) stageReasons = view.optionsSummary.reasonCodes;
  else if (['TRADEABLE', 'NOT_TRADEABLE', 'EXPIRED'].includes(view.state)) stageReasons = view.tradeabilitySummary.reasonCodes;
  const reason = [...stageReasons, ...view.reasons].find(value => typeof value === 'string' && value.trim());
  if (!reason) return 'No failed gate summary supplied.';
  return reasonLabels[reason] || readable(reason);
}

function humanizeBlockedReason(canonical) {
  if (canonical.publicationState !== 'BLOCKED' && canonical.state !== 'BLOCKED') return null;
  const reason = canonical.reasons[0] ?? null;
  if (!reason) return 'Canonical evaluation blocked — reason unavailable.';
  return reasonLabels[reason] || readable(reason);
}

function buildHtfContext(canonical) {
  const htf = canonical.htfFactor ?? null;
  if (!htf) return null;
  const contribution = htf.contribution;
  const direction = contribution == null ? 'UNAVAILABLE'
    : contribution > 0.02 ? 'ALIGNED'
      : contribution < -0.02 ? 'OPPOSING'
        : 'NEUTRAL';
  return {
    factorId: htf.factorId,
    contribution,
    direction,
    detail: htf.detail,
    availability: htf.availability,
    available: htf.available,
  };
}

export function readable(value) {
  if (value == null || value === '') return 'unavailable';
  return String(value).replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, character => character.toUpperCase());
}
