export const previewStates = [
  'NO_SETUP',
  'WATCH',
  'ARMED',
  'TRIGGERED',
  'TRADEABLE',
  'OPTIONS_NOT_SUITABLE',
  'BLOCKED',
  'PORTFOLIO_VETOED',
  'PORTFOLIO_APPROVED',
];

const evaluationTimestamp = '2026-09-16T14:35:00Z';

export function createQxV2PreviewFixture(state = 'NO_SETUP', symbol = 'SPY') {
  const normalizedState = previewStates.includes(state) ? state : 'NO_SETUP';
  const payload = {
    symbol,
    timeframe: '5m',
    evaluation_timestamp: evaluationTimestamp,
    request_started_at: '2026-09-16T14:34:58Z',
    publication_state: normalizedState === 'BLOCKED' ? 'BLOCKED' : 'RESEARCH_ONLY',
    pipeline_version: 'core_v1',
    config_version: 'research_v1',
    current_lifecycle_state: normalizedState,
    reason_codes: reasonCodes(normalizedState),
    evidence_summary: ['Fixture payload for deterministic Track 2F visual review.'],
    structure: {
      regime: 'BULLISH',
      structure_score: 74,
      latest_bos: 'BULLISH_BOS',
      latest_choch: null,
      latest_event: {
        event_type: 'BULLISH_BOS', event_timestamp: '2026-09-16T14:25:00Z',
        knowledge_timestamp: '2026-09-16T14:30:00Z',
      },
      protected_low: {price: 445, knowledge_timestamp: '2026-09-16T14:20:00Z'},
      protected_high: null,
      order_blocks: [{
        order_block_id: `${symbol}-OB-17`,
        evidence_ladder: {displacement_atr: 1.8, validation: {event_id: `${symbol}-BOS-4`}},
      }],
    },
    market_regime: {
      trend: 'TRENDING_UP',
      volatility: 'NORMAL',
      gamma: 'POSITIVE_GAMMA',
      session: 'OPENING',
      trend_evidence: {ema_stack: 'BULLISH_ALIGNED'},
      volatility_evidence: {atr_percentile: 0.58},
      gamma_evidence: {source: 'BROKER_SNAPSHOT'},
      session_evidence: {window: 'RTH_OPEN'},
    },
    direction: {
      direction_label: 'BULLISH',
      direction_score: 68,
      direction_evidence_coverage: 0.86,
      coverage_status: 'STRONG',
      factors: [{factor_name: 'structure', detail: 'Bullish structure aligned'}],
    },
    playbooks: [],
    stage_latencies: baseLatencies(),
    data_dependencies: {
      bars: {
        name: 'bars', available: true, source: 'local_bar_cache', freshness: 'POINT_IN_TIME',
        publication_state: 'RESEARCH_ONLY', sync_status: 'SYNCED', data_as_of: evaluationTimestamp,
        cache_status: 'HIT',
      },
      option_chain: {
        name: 'option_chain', available: false, source: 'UNAVAILABLE', freshness: 'UNAVAILABLE',
        publication_state: 'BLOCKED', sync_status: 'UNAVAILABLE', reason_code: 'OPTION_CHAIN_UNAVAILABLE',
        cache_status: 'MISS',
      },
    },
  };

  if (normalizedState === 'NO_SETUP') return payload;
  if (normalizedState === 'BLOCKED') {
    payload.trigger = {
      state: 'NO_SETUP', publication_state: 'BLOCKED', trigger_price: 450,
      invalidation_price: 445, evidence_ladder: {reason: 'BLOCKED_PUBLICATION_STATE'},
    };
    payload.stage_latencies.trigger_ms = 0.42;
    return payload;
  }

  const playbookState = normalizedState === 'WATCH' ? 'WATCH' : 'ARMED';
  const playbook = {
    playbook_id: 'playbook_a_pullback',
    state: playbookState,
    reason_code: playbookState === 'WATCH' ? 'SETUP_DEVELOPING' : 'SETUP_FORMED_WAITING_FOR_TRIGGER',
    trigger_definition: 'Completed 5m close above validated order block',
    trigger_price: 450,
    invalidation_price: 445,
    invalidation_source_type: 'ORDER_BLOCK_DISTAL',
    rule_results: [previewRule('QX-PB-101', 'PLAYBOOK_STRUCTURE', true, 'Validated order block', `${symbol}-OB-17`)],
  };
  payload.playbooks = [playbook];
  payload.primary_playbook_candidate = playbook;
  payload.stage_latencies.playbooks_ms = 1.12;
  if (normalizedState === 'WATCH') return payload;

  payload.trigger = normalizedState === 'ARMED'
    ? {
      state: 'ARMED', publication_state: 'RESEARCH_ONLY', trigger_price: 450,
      invalidation_price: 445, trigger_event: null, evidence_ladder: {reason: 'WAITING_FOR_TRIGGER'},
    }
    : triggeredResult(symbol);
  payload.stage_latencies.trigger_ms = 0.74;
  if (normalizedState === 'ARMED' || normalizedState === 'TRIGGERED') return payload;

  payload.tradeability = {
    state: 'TRADEABLE', publication_state: 'RESEARCH_ONLY', trigger_price: 450,
    invalidation_price: 445, participation_score: 78,
    participation_evidence_coverage: 0.82, risk_reward_to_best_structural_target: 2.35,
    observed_entry_reference_price: 451.25, target_candidates: [461.75],
    reason_codes: ['TRADEABLE_ALL_GATES_PASS'],
    evidence_ladder: {rvol_normalized: 1.42, spread_pct: 0.0018, target_price: 461.75},
  };
  payload.stage_latencies.tradeability_ms = 1.46;
  if (normalizedState === 'TRADEABLE') return payload;

  if (normalizedState === 'OPTIONS_NOT_SUITABLE') {
    markOptionDependencyAvailable(payload);
    payload.options_expression = {
      state: 'NOT_SUITABLE', publication_state: 'RESEARCH_ONLY',
      data_as_of: evaluationTimestamp, candidate_strategies: [], primary_candidate_id: null,
      reason_codes: ['OPTIONS_EXPRESSION_NOT_SUITABLE'],
      evidence_ladder: {iv_rank: 91, candidate_count: 0},
    };
    payload.stage_latencies.options_expression_ms = 2.18;
    return payload;
  }

  payload.options_expression = {
    state: 'SUITABLE', publication_state: 'RESEARCH_ONLY', reason_codes: ['OPTIONS_EXPRESSION_SUITABLE'],
    data_as_of: evaluationTimestamp,
    primary_candidate_id: `${symbol}-CALL-SPREAD`,
    candidate_strategies: [{
      candidate_id: `${symbol}-CALL-SPREAD`, strategy_type: 'CALL_DEBIT_SPREAD', direction: 'BULLISH',
      expiration: '2026-10-16', dte: 30, max_loss: 240, max_profit: 510,
      evidence_ladder: {liquidity_status: 'PASS'},
    }],
    evidence_ladder: {iv_rank: 34, candidate_count: 1},
  };
  markOptionDependencyAvailable(payload);
  payload.stage_latencies.options_expression_ms = 2.18;
  payload.portfolio_risk = {
    state: normalizedState,
    binding_constraint: normalizedState === 'PORTFOLIO_VETOED' ? 'SECTOR_CONCENTRATION' : 'MAX_RISK_PER_TRADE',
    approved_contracts_cap: normalizedState === 'PORTFOLIO_APPROVED' ? 2 : 0,
    reason_codes: [normalizedState === 'PORTFOLIO_APPROVED' ? 'PORTFOLIO_RISK_APPROVED' : 'SECTOR_CONCENTRATION_LIMIT'],
    evidence_ladder: {account_snapshot: 'SYNCED', requested_contracts: 2},
    data_as_of: evaluationTimestamp,
  };
  payload.data_dependencies.account_snapshot = {
    name: 'account_snapshot', available: true, source: 'fixture_account_snapshot',
    freshness: 'POINT_IN_TIME', publication_state: 'RESEARCH_ONLY', sync_status: 'SYNCED',
    data_as_of: evaluationTimestamp, cache_status: 'HIT',
  };
  payload.stage_latencies.portfolio_risk_ms = 0.91;
  return payload;
}

function triggeredResult(symbol) {
  return {
    state: 'TRIGGERED', publication_state: 'RESEARCH_ONLY', trigger_price: 450,
    invalidation_price: 445, trigger_event_timestamp: '2026-09-16T14:30:00Z',
    trigger_event: {
      trigger_event_id: `${symbol}-TRIGGER-9`, trigger_rule_type: 'CLOSE_ABOVE_LEVEL',
      event_timestamp: '2026-09-16T14:30:00Z', confirmation_method: 'BAR_CLOSE_CONFIRMED',
      rule_results: [previewRule('QX-TRIG-002', 'TRIGGER_CLOSE', true, 'Close above 450', 451.25)],
    },
    evidence_ladder: {observed_price: 451.25, gap_beyond_trigger: false},
  };
}

function previewRule(ruleId, category, passed, requiredValue, observedValue) {
  return {
    rule_id: ruleId,
    rule_version: '1.0',
    category,
    required_value: requiredValue,
    observed_value: observedValue,
    passed,
    severity: 'HARD',
    hard_gate: true,
    weight: 0.3,
    contribution: passed ? 0.3 : 0,
    data_source: 'BAR_DERIVED',
    event_timestamp: '2026-09-16T14:30:00Z',
    knowledge_timestamp: '2026-09-16T14:30:00Z',
    detail: 'Deterministic preview evidence — not a live market result.',
  };
}

function baseLatencies() {
  return {
    structure_ms: 1.25,
    regime_ms: 0.62,
    direction_ms: 0.88,
    playbooks_ms: 'SKIPPED',
    trigger_ms: 'SKIPPED',
    tradeability_ms: 'SKIPPED',
    options_expression_ms: 'SKIPPED',
    portfolio_risk_ms: 'SKIPPED',
    total_ms: 2.75,
  };
}

function markOptionDependencyAvailable(payload) {
  payload.data_dependencies.option_chain = {
    name: 'option_chain', available: true, source: 'fixture_option_chain', freshness: 'POINT_IN_TIME',
    publication_state: 'RESEARCH_ONLY', sync_status: 'SYNCED', data_as_of: evaluationTimestamp,
    cache_status: 'HIT',
  };
}

function reasonCodes(state) {
  const codes = {
    NO_SETUP: ['NO_SETUP'],
    WATCH: ['SETUP_DEVELOPING'],
    ARMED: ['SETUP_FORMED_WAITING_FOR_TRIGGER'],
    TRIGGERED: ['TRIGGER_CONFIRMED'],
    TRADEABLE: ['TRADEABLE_ALL_GATES_PASS'],
    OPTIONS_NOT_SUITABLE: ['OPTIONS_EXPRESSION_NOT_SUITABLE'],
    BLOCKED: ['BLOCKED_PUBLICATION_STATE'],
    PORTFOLIO_VETOED: ['SECTOR_CONCENTRATION_LIMIT'],
    PORTFOLIO_APPROVED: ['PORTFOLIO_RISK_APPROVED'],
  };
  return codes[state] || [];
}
