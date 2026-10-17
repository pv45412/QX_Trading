export const lifecycleStates = [
  'BLOCKED',
  'NO_SETUP',
  'WATCH',
  'ARMED',
  'TRIGGERED',
  'NOT_TRADEABLE',
  'TRADEABLE',
  'OPTIONS_NOT_SUITABLE',
  'OPTIONS_SUITABLE',
  'PORTFOLIO_VETOED',
  'PORTFOLIO_APPROVED',
  'EXPIRED',
];

export const lifecyclePath = [
  'WATCH',
  'ARMED',
  'TRIGGERED',
  'TRADEABLE',
  'OPTIONS_SUITABLE',
  'PORTFOLIO_APPROVED',
];

const terminalStates = new Set([
  'BLOCKED',
  'NO_SETUP',
  'NOT_TRADEABLE',
  'OPTIONS_NOT_SUITABLE',
  'PORTFOLIO_VETOED',
  'EXPIRED',
]);

const stages = [
  ['structure', 'Structure'],
  ['market_regime', 'Regime'],
  ['direction', 'Direction'],
  ['playbooks', 'Playbooks'],
  ['trigger', 'Trigger'],
  ['tradeability', 'Tradeability'],
  ['options_expression', 'Options'],
  ['portfolio_risk', 'Portfolio'],
];

const latencyKeys = {
  structure: 'structure_ms',
  market_regime: 'regime_ms',
  direction: 'direction_ms',
  playbooks: 'playbooks_ms',
  trigger: 'trigger_ms',
  tradeability: 'tradeability_ms',
  options_expression: 'options_expression_ms',
  portfolio_risk: 'portfolio_risk_ms',
};

export function adaptQxV2Evaluation(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const playbook = payload.primary_playbook_candidate || null;
  const direction = payload.direction || null;
  const trigger = payload.trigger || null;
  const tradeability = payload.tradeability || null;
  const optionsExpression = payload.options_expression || null;
  const portfolioRisk = payload.portfolio_risk || null;
  const primaryOptionCandidate = Array.isArray(optionsExpression?.candidate_strategies)
    ? optionsExpression.candidate_strategies.find(candidate => candidate.candidate_id === optionsExpression.primary_candidate_id) || null
    : null;
  const state = payload.current_lifecycle_state
    ? String(payload.current_lifecycle_state)
    : 'UNAVAILABLE';
  const reasons = unique([
    ...(payload.reason_codes || []),
    playbook?.reason_code,
    ...(trigger?.reason_codes || []),
    ...(tradeability?.reason_codes || []),
    ...(payload.options_expression?.reason_codes || []),
    ...(payload.portfolio_risk?.reason_codes || []),
  ]);
  const evidence = uniqueEvidence([
    ...(payload.evidence_summary || []).map((value, index) => ({
      stage: 'Pipeline',
      key: `summary_${index + 1}`,
      value: printable(value),
    })),
    ...(direction?.factors || []).map(factor => ({
      stage: 'Direction',
      key: factor.factor_name || factor.factor_id || 'factor',
      value: printable(factor.detail || factor.weighted_contribution),
    })),
    ...flattenStructureEvidence(payload.structure),
    ...flattenRegimeEvidence(payload.market_regime),
    ...(payload.playbooks || []).flatMap(item => [
      ...flattenEvidence('Playbook', item?.evidence_ladder),
      ...flattenRuleResults('Playbook', item?.rule_results),
    ]),
    ...flattenEvidence('Trigger', trigger?.evidence_ladder),
    ...flattenRuleResults('Trigger', trigger?.trigger_event?.rule_results),
    ...flattenEvidence('Tradeability', tradeability?.evidence_ladder),
    ...flattenEvidence('Options', payload.options_expression?.evidence_ladder),
    ...flattenEvidence('Portfolio', payload.portfolio_risk?.evidence_ladder),
  ]);
  const stageAvailability = stages.map(([key, label]) => {
    const output = key === 'playbooks' ? payload.playbooks : payload[key];
    const latency = payload.stage_latencies?.[latencyKeys[key]];
    const outputState = String(output?.state || '');
    const publicationState = String(output?.publication_state || '');
    const arrayContainsBlockedResult = Array.isArray(output) && output.some(item => (
      String(item?.state || '') === 'BLOCKED'
      || String(item?.publication_state || '') === 'BLOCKED'
    ));
    return {
      key,
      label,
      status: outputState === 'BLOCKED' || publicationState === 'BLOCKED' || arrayContainsBlockedResult
        ? 'BLOCKED'
        : latency === 'SKIPPED'
          ? 'SKIPPED'
          : output != null ? 'AVAILABLE' : 'UNAVAILABLE',
      latencyMs: Number.isFinite(latency) ? latency : null,
    };
  });
  const triggerConfirmationProhibited = new Set(['BLOCKED', 'NO_SETUP', 'WATCH', 'ARMED', 'EXPIRED']).has(state)
    || String(trigger?.publication_state || '') === 'BLOCKED';
  const triggerEvent = trigger?.trigger_event;
  const hasCanonicalTriggerEvent = Boolean(triggerEvent && typeof triggerEvent === 'object'
    && typeof triggerEvent.trigger_event_id === 'string' && triggerEvent.trigger_event_id.trim() !== ''
    && typeof triggerEvent.event_timestamp === 'string' && triggerEvent.event_timestamp.trim() !== ''
    && typeof triggerEvent.confirmation_method === 'string' && triggerEvent.confirmation_method.trim() !== '');
  const triggerConfirmed = !triggerConfirmationProhibited
    && hasCanonicalTriggerEvent
    && (state === 'TRIGGERED' || String(trigger?.state || '') === 'TRIGGERED');
  return {
    symbol: String(payload.symbol || ''),
    timeframe: payload.timeframe ?? null,
    horizon: payload.horizon ?? null,
    htfTimeframe: payload.htf_timeframe ?? null,
    macroTimeframe: payload.macro_timeframe ?? null,
    state,
    stateCategory: state === 'UNAVAILABLE'
      ? 'unavailable'
      : terminalStates.has(state) ? 'terminal' : 'progressive',
    publicationState: String(payload.publication_state || 'UNKNOWN'),
    pipelineVersion: String(payload.pipeline_version || 'UNKNOWN'),
    evaluationId: payload.evaluation_id ?? null,
    evaluationTimestamp: payload.evaluation_timestamp || null,
    requestStartedAt: payload.request_started_at || null,
    marketRegime: {
      trend: payload.market_regime?.trend ?? null,
      volatility: payload.market_regime?.volatility ?? null,
      gamma: payload.market_regime?.gamma ?? null,
      session: payload.market_regime?.session ?? null,
    },
    structureSummary: {
      bias: payload.structure?.regime ?? null,
      score: finiteOrNull(payload.structure?.structure_score),
      latestBos: payload.structure?.latest_bos ?? null,
      latestChoch: payload.structure?.latest_choch ?? null,
      latestEventType: payload.structure?.latest_event?.event_type ?? null,
      latestEventTimestamp: payload.structure?.latest_event?.event_timestamp ?? null,
      latestKnowledgeTimestamp: payload.structure?.latest_event?.knowledge_timestamp ?? null,
      protectedHigh: finiteOrNull(payload.structure?.protected_high?.price),
      protectedHighTimestamp: payload.structure?.protected_high?.knowledge_timestamp ?? null,
      protectedLow: finiteOrNull(payload.structure?.protected_low?.price),
      protectedLowTimestamp: payload.structure?.protected_low?.knowledge_timestamp ?? null,
    },
    playbook: playbook?.playbook_id || 'UNAVAILABLE',
    playbookState: playbook?.state ?? null,
    directionLabel: direction?.direction_label || 'UNAVAILABLE',
    directionScore: finiteOrNull(direction?.direction_score),
    evidenceCoverage: finiteOrNull(direction?.direction_evidence_coverage),
    coverageStatus: direction?.coverage_status || 'UNAVAILABLE',
    marketDriver: payload.market_driver ?? null,
    htfFactor: extractHtfFactor(direction),

    trigger: finiteOrNull(trigger?.trigger_price ?? playbook?.trigger_price),
    invalidation: finiteOrNull(trigger?.invalidation_price ?? playbook?.invalidation_price),
    triggerConfirmed,
    triggerSource: triggerConfirmed
      ? 'CONFIRMED'
      : trigger ? 'UNCONFIRMED' : playbook ? 'PLANNED' : 'UNAVAILABLE',
    triggerCondition: trigger?.trigger_event?.trigger_rule_type ?? playbook?.trigger_definition ?? null,
    triggerEventTimestamp: trigger?.trigger_event?.event_timestamp ?? trigger?.trigger_event_timestamp ?? null,
    triggerKnowledgeTimestamp: trigger?.trigger_event?.knowledge_timestamp ?? null,
    invalidationCondition: playbook?.invalidation_source_type ?? null,
    tradeabilitySummary: {
      state: tradeability?.state ?? null,
      participationScore: finiteOrNull(tradeability?.participation_score),
      participationCoverage: finiteOrNull(tradeability?.participation_evidence_coverage),
      structuralRiskReward: finiteOrNull(
        tradeability?.risk_reward_to_best_structural_target
          ?? tradeability?.risk_reward_to_target1,
      ),
      observedEntryReference: finiteOrNull(tradeability?.observed_entry_reference_price),
      targetCandidates: Array.isArray(tradeability?.target_candidates)
        ? tradeability.target_candidates.map(finiteOrNull).filter(value => value != null)
        : [],
      reasonCodes: Array.isArray(tradeability?.reason_codes) ? [...tradeability.reason_codes] : [],
    },
    optionsSummary: {
      state: optionsExpression?.state ?? null,
      candidateCount: Array.isArray(optionsExpression?.candidate_strategies)
        ? optionsExpression.candidate_strategies.length
        : null,
      strategyType: primaryOptionCandidate?.strategy_type ?? null,
      expiration: primaryOptionCandidate?.expiration ?? null,
      maxLoss: finiteOrNull(primaryOptionCandidate?.max_loss),
      maxProfit: finiteOrNull(primaryOptionCandidate?.max_profit),
      dataAsOf: optionsExpression?.data_as_of ?? null,
      publicationState: optionsExpression?.publication_state ?? null,
      reasonCodes: Array.isArray(optionsExpression?.reason_codes) ? [...optionsExpression.reason_codes] : [],
    },
    portfolioSummary: {
      state: portfolioRisk?.state ?? null,
      bindingConstraint: portfolioRisk?.binding_constraint ?? null,
      approvedContractsCap: finiteOrNull(portfolioRisk?.approved_contracts_cap),
      dataAsOf: portfolioRisk?.data_as_of ?? null,
      publicationState: portfolioRisk?.publication_state ?? null,
      evidenceStatus: portfolioRisk?.evidence_ladder?.account_snapshot ?? null,
      reasonCodes: Array.isArray(portfolioRisk?.reason_codes) ? [...portfolioRisk.reason_codes] : [],
    },
    reasons,
    evidence,
    stageAvailability,
    dependencies: Object.values(payload.data_dependencies || {}).map(dependency => ({
      name: dependency.name || 'dependency',
      available: dependency.available === true,
      source: dependency.source || 'UNAVAILABLE',
      freshness: dependency.freshness || 'UNAVAILABLE',
      syncStatus: dependency.sync_status || 'UNAVAILABLE',
      publicationState: dependency.publication_state || 'BLOCKED',
      reason: dependency.reason_code || null,
      dataAsOf: dependency.data_as_of || null,
      snapshotId: dependency.snapshot_id ?? null,
      cacheStatus: dependency.cache_status || 'UNKNOWN',
    })),
    totalMs: finiteOrNull(payload.stage_latencies?.total_ms),
  };
}

function flattenRuleResults(stage, rules) {
  if (!Array.isArray(rules)) return [];
  return rules.map((rule, index) => {
    const ruleIdentity = buildRuleIdentity(stage, rule);
    const ruleResult = {
      rule_id: rule.rule_id ?? `rule_${index + 1}`,
      rule_version: rule.rule_version ?? null,
      category: rule.category ?? null,
      required_value: rule.required_value ?? null,
      observed_value: rule.observed_value ?? null,
      passed: rule.passed,
      severity: rule.severity ?? null,
      hard_gate: rule.hard_gate ?? null,
      weight: rule.weight ?? null,
      contribution: rule.contribution ?? null,
      data_source: rule.data_source ?? null,
      event_timestamp: rule.event_timestamp ?? null,
      knowledge_timestamp: rule.knowledge_timestamp ?? null,
      detail: rule.detail ?? null,
      source_stage: stage.toUpperCase(),
    };
    return {
      stage,
      source_stage: ruleResult.source_stage,
      type: 'RULE_RESULT',
      key: ruleResult.rule_id,
      value: printable(ruleResult),
      ruleResult,
      ruleIdentity,
    };
  });
}

function flattenStructureEvidence(structure) {
  if (!structure || typeof structure !== 'object') return [];
  const orderBlocks = Array.isArray(structure.order_blocks) ? structure.order_blocks : [];
  const distinctBlocks = orderBlocks.length > 0
    ? orderBlocks
    : [structure.demand_ob, structure.supply_ob].filter(Boolean);
  return distinctBlocks.flatMap((block, index) => flattenEvidence(
    'Structure',
    block?.evidence_ladder,
    `order_block_${block?.order_block_id || index + 1}`,
  ));
}

function flattenRegimeEvidence(regime) {
  if (!regime || typeof regime !== 'object') return [];
  return [
    ...flattenEvidence('Regime', regime.trend_evidence, 'trend'),
    ...flattenEvidence('Regime', regime.volatility_evidence, 'volatility'),
    ...flattenEvidence('Regime', regime.gamma_evidence, 'gamma'),
    ...flattenEvidence('Regime', regime.session_evidence, 'session'),
  ];
}

function flattenEvidence(stage, ladder, prefix = '') {
  if (!ladder || typeof ladder !== 'object') return [];
  return Object.entries(ladder).flatMap(([key, value]) => {
    const evidenceKey = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return Object.entries(value).map(([nestedKey, nestedValue]) => ({
        stage,
        key: `${evidenceKey}.${nestedKey}`,
        value: printable(nestedValue),
      }));
    }
    return [{stage, key: evidenceKey, value: printable(value)}];
  });
}

function unique(values) {
  return [...new Set(values.filter(value => typeof value === 'string' && value.trim()))];
}

function uniqueEvidence(items) {
  const seen = new Set();
  return items.filter(item => {
    if (item.type !== 'RULE_RESULT') return true;
    const identity = item.ruleIdentity;
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function buildRuleIdentity(stage, sourceRule) {
  return JSON.stringify([
    stage.toUpperCase(),
    sourceRule.rule_id,
    sourceRule.rule_version,
    sourceRule.event_timestamp,
    sourceRule.knowledge_timestamp,
  ].map(encodeIdentityPart));
}

function encodeIdentityPart(value) {
  if (value === null) return 'null:';
  if (value === undefined) return 'undefined:';
  return `${typeof value}:${String(value)}`;
}

function printable(value) {
  if (value == null) return 'UNAVAILABLE';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

function extractHtfFactor(direction) {
  if (!direction || !Array.isArray(direction.factors)) return null;
  const htf = direction.factors.find(f =>
    f.factor_id === 'higher_timeframe' || f.factor_name === 'higher_timeframe',
  );
  if (!htf) return null;
  const availability = htf.availability ?? htf.factor_availability ?? 'UNAVAILABLE';
  return {
    factorId: htf.factor_id || htf.factor_name || 'higher_timeframe',
    contribution: finiteOrNull(htf.weighted_contribution),
    detail: htf.detail ?? null,
    reliability: finiteOrNull(htf.reliability),
    available: availability !== 'UNAVAILABLE',
    availability,
  };
}

function finiteOrNull(value) {

  if (value == null || typeof value === 'boolean') return null;
  if (typeof value === 'string' && value.trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
