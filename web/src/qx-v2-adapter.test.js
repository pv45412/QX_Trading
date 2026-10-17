import test from 'node:test';
import assert from 'node:assert/strict';

import {adaptQxV2Evaluation, lifecycleStates} from './qx-v2-adapter.js';

function payload(state) {
  return {
    symbol: 'SPY',
    current_lifecycle_state: state,
    publication_state: 'RESEARCH_ONLY',
    pipeline_version: 'core_v1',
    primary_playbook_candidate: {
      playbook_id: 'playbook_a_pullback',
      trigger_price: 450,
      invalidation_price: 445,
      reason_code: 'PLAYBOOK_ARMED',
    },
    direction: {
      direction_label: 'BULLISH',
      direction_score: 65,
      direction_evidence_coverage: 0.75,
      coverage_status: 'STRONG',
      factors: [{factor_name: 'trend', detail: 'aligned'}],
    },
    reason_codes: ['PIPELINE_REASON'],
    evidence_summary: ['deterministic'],
    stage_latencies: {structure_ms: 1.25, options_expression_ms: 'SKIPPED'},
  };
}

test('adapter renders every canonical lifecycle state', () => {
  for (const state of lifecycleStates) {
    assert.equal(adaptQxV2Evaluation(payload(state)).state, state);
  }
});

test('missing lifecycle state remains unavailable and expired is explicit', () => {
  assert.equal(adaptQxV2Evaluation({symbol: 'SPY'}).state, 'UNAVAILABLE');
  assert.equal(adaptQxV2Evaluation({current_lifecycle_state: 'EXPIRED'}).state, 'EXPIRED');
  assert.ok(lifecycleStates.includes('EXPIRED'));
});

test('adapter exposes reasons, evidence, and skipped stage status', () => {
  const view = adaptQxV2Evaluation(payload('ARMED'));

  assert.deepEqual(view.reasons, ['PIPELINE_REASON', 'PLAYBOOK_ARMED']);
  assert.ok(view.evidence.some(item => item.key === 'trend'));
  assert.equal(
    view.stageAvailability.find(stage => stage.key === 'options_expression').status,
    'SKIPPED',
  );
});

test('adapter reads canonical HTF availability without contradicting contribution', () => {
  const input = payload('WATCH');
  input.horizon = 'DAY';
  input.htf_timeframe = '1h';
  input.macro_timeframe = '1d';
  input.direction.factors.push({
    factor_id: 'higher_timeframe',
    availability: 'AVAILABLE',
    weighted_contribution: 10,
    reliability: 1,
    detail: 'HTF confirmed structure state: BULLISH',
  });

  const view = adaptQxV2Evaluation(input);

  assert.equal(view.htfFactor.availability, 'AVAILABLE');
  assert.equal(view.htfFactor.available, true);
  assert.equal(view.htfFactor.contribution, 10);
  assert.equal(view.horizon, 'DAY');
  assert.equal(view.htfTimeframe, '1h');
  assert.equal(view.macroTimeframe, '1d');
});

test('missing numeric fields stay unavailable instead of becoming zero', () => {
  const view = adaptQxV2Evaluation({
    symbol: 'SPY',
    current_lifecycle_state: 'NO_SETUP',
    direction: {direction_score: null, direction_evidence_coverage: null},
  });

  assert.equal(view.directionScore, null);
  assert.equal(view.evidenceCoverage, null);
  assert.equal(view.trigger, null);
  assert.equal(view.invalidation, null);
});

test('whitespace and boolean numeric fields remain unavailable', () => {
  const view = adaptQxV2Evaluation({
    symbol: 'SPY',
    current_lifecycle_state: 'NO_SETUP',
    direction: {direction_score: '   ', direction_evidence_coverage: false},
    trigger: {trigger_price: true, invalidation_price: '\t'},
  });

  assert.equal(view.directionScore, null);
  assert.equal(view.evidenceCoverage, null);
  assert.equal(view.trigger, null);
  assert.equal(view.invalidation, null);
});

test('adapter exposes dependency freshness and provenance without fabrication', () => {
  const input = payload('OPTIONS_NOT_SUITABLE');
  input.options_expression = {state: 'BLOCKED', reason_codes: ['CHAIN_STALE']};
  input.data_dependencies = {
    option_chain: {
      name: 'option_chain',
      available: false,
      source: 'schwab',
      freshness: 'STALE',
      publication_state: 'BLOCKED',
      sync_status: 'PARTIAL',
      reason_code: 'OPTION_CHAIN_UNAVAILABLE',
      data_as_of: '2026-09-16T14:00:00Z',
      snapshot_id: 42,
      cache_status: 'HIT',
    },
  };

  const view = adaptQxV2Evaluation(input);
  const dependency = view.dependencies[0];

  assert.equal(dependency.freshness, 'STALE');
  assert.equal(dependency.publicationState, 'BLOCKED');
  assert.equal(dependency.snapshotId, 42);
  assert.equal(dependency.cacheStatus, 'HIT');
  assert.equal(
    view.stageAvailability.find(stage => stage.key === 'options_expression').status,
    'BLOCKED',
  );
});

test('planned levels are labeled and rule evidence spans upstream stages', () => {
  const input = payload('ARMED');
  input.structure = {
    order_blocks: [{
      order_block_id: 'OB_42',
      evidence_ladder: {displacement_atr: 1.8, validation: {event_id: 'BOS_7'}},
    }],
  };
  input.market_regime = {
    trend_evidence: {ema_stack: 'BULLISH'},
    volatility_evidence: {atr_percentile: 0.62},
    gamma_evidence: {},
    session_evidence: {session: 'OPENING'},
  };
  input.playbooks = [{
    rule_results: [{rule_id: 'PLAYBOOK_SCORE', passed: true, observed_value: 80}],
  }];
  input.stage_latencies.trigger_ms = 'SKIPPED';

  const view = adaptQxV2Evaluation(input);

  assert.equal(view.triggerSource, 'PLANNED');
  assert.ok(view.evidence.some(item => item.key === 'order_block_OB_42.displacement_atr'));
  assert.ok(view.evidence.some(item => item.key === 'order_block_OB_42.validation.event_id'));
  assert.ok(view.evidence.some(item => item.key === 'trend.ema_stack'));
  assert.ok(view.evidence.some(item => item.key === 'volatility.atr_percentile'));
  assert.ok(view.evidence.some(item => item.key === 'session.session'));
  assert.ok(view.evidence.some(item => item.key === 'PLAYBOOK_SCORE'));
  assert.equal(
    view.stageAvailability.find(stage => stage.key === 'trigger').status,
    'SKIPPED',
  );
});

test('test_trigger_object_presence_does_not_imply_triggered', () => {
  const input = payload('ARMED');
  input.trigger = {state: 'ARMED', trigger_price: 450, trigger_event: {}};

  const view = adaptQxV2Evaluation(input);

  assert.equal(view.triggerConfirmed, false);
  assert.equal(view.triggerSource, 'UNCONFIRMED');
});

test('test_armed_trigger_renders_unconfirmed', () => {
  const input = payload('ARMED');
  input.trigger = {state: 'ARMED', trigger_price: 450};

  assert.equal(adaptQxV2Evaluation(input).triggerSource, 'UNCONFIRMED');
});

test('test_triggered_state_without_canonical_event_remains_unconfirmed', () => {
  const input = payload('TRIGGERED');
  input.trigger = {state: 'TRIGGERED', trigger_price: 450};

  const view = adaptQxV2Evaluation(input);

  assert.equal(view.triggerConfirmed, false);
  assert.equal(view.triggerSource, 'UNCONFIRMED');
});

test('test_triggered_state_with_canonical_event_renders_confirmed', () => {
  const input = payload('TRIGGERED');
  input.trigger = {
    state: 'TRIGGERED',
    trigger_price: 450,
    trigger_event: {
      trigger_event_id: 'SPY-TRIGGER-1',
      event_timestamp: '2026-09-16T14:00:00Z',
      confirmation_method: 'BAR_CLOSE_CONFIRMED',
    },
  };

  const view = adaptQxV2Evaluation(input);

  assert.equal(view.triggerConfirmed, true);
  assert.equal(view.triggerSource, 'CONFIRMED');
});

test('adapter preserves evaluation identity without fabricating it', () => {
  assert.equal(adaptQxV2Evaluation({...payload('WATCH'), evaluation_id: 'eval-1'}).evaluationId, 'eval-1');
  assert.equal(adaptQxV2Evaluation(payload('WATCH')).evaluationId, null);
});

test('test_blocked_trigger_never_renders_confirmed', () => {
  const input = payload('BLOCKED');
  input.trigger = {
    state: 'TRIGGERED',
    publication_state: 'BLOCKED',
    trigger_event: {confirmed_at: '2026-09-16T14:00:00Z'},
  };

  const view = adaptQxV2Evaluation(input);

  assert.equal(view.triggerConfirmed, false);
  assert.equal(view.triggerSource, 'UNCONFIRMED');
});

function triggerRulePayload() {
  const input = payload('TRIGGERED');
  input.trigger = {
    state: 'TRIGGERED',
    publication_state: 'VERIFIED',
    trigger_event: {
      rule_results: [{
        rule_id: 'QX-TRIG-002',
        rule_version: '1.2',
        category: 'TRIGGER_CLOSE',
        required_value: 'close above 450',
        observed_value: 451.25,
        passed: true,
        severity: 'HARD',
        hard_gate: true,
        data_source: 'BAR_DERIVED',
        event_timestamp: '2026-09-16T14:00:00Z',
        knowledge_timestamp: '2026-09-16T14:00:01Z',
        detail: 'Confirmed on completed bar',
      }],
    },
  };
  return input;
}

test('test_trigger_rule_results_exposed_to_evidence_model', () => {
  const rule = adaptQxV2Evaluation(triggerRulePayload()).evidence
    .find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.type, 'RULE_RESULT');
  assert.equal(rule.ruleResult.rule_version, '1.2');
  assert.equal(rule.ruleResult.category, 'TRIGGER_CLOSE');
  assert.equal(rule.ruleResult.required_value, 'close above 450');
  assert.equal(rule.ruleResult.observed_value, 451.25);
  assert.equal(rule.ruleResult.detail, 'Confirmed on completed bar');
});

test('test_trigger_rule_result_preserves_pass_fail_semantics', () => {
  const rule = adaptQxV2Evaluation(triggerRulePayload()).evidence
    .find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.passed, true);
  assert.equal(rule.ruleResult.severity, 'HARD');
  assert.equal(rule.ruleResult.hard_gate, true);
});

test('test_trigger_rule_result_preserves_provenance', () => {
  const rule = adaptQxV2Evaluation(triggerRulePayload()).evidence
    .find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.data_source, 'BAR_DERIVED');
  assert.equal(rule.ruleResult.event_timestamp, '2026-09-16T14:00:00Z');
  assert.equal(rule.ruleResult.knowledge_timestamp, '2026-09-16T14:00:01Z');
});

test('test_trigger_evidence_source_stage_is_trigger', () => {
  const rule = adaptQxV2Evaluation(triggerRulePayload()).evidence
    .find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.stage, 'Trigger');
  assert.equal(rule.source_stage, 'TRIGGER');
  assert.equal(rule.ruleResult.source_stage, 'TRIGGER');
});

test('test_trigger_rule_result_preserves_weight', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].weight = 0.35;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.weight, 0.35);
});

test('test_trigger_rule_result_preserves_contribution', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].contribution = -0.12;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.contribution, -0.12);
});

test('test_null_weight_remains_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].weight = null;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.weight, null);
});

test('test_null_contribution_remains_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].contribution = null;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.contribution, null);
});

test('test_empty_event_timestamp_preserved_as_empty_string', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].event_timestamp = '';
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.event_timestamp, '');
});

test('test_empty_knowledge_timestamp_preserved_as_empty_string', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].knowledge_timestamp = '';
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.knowledge_timestamp, '');
});

test('test_null_event_timestamp_remains_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].event_timestamp = null;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.event_timestamp, null);
});

test('test_null_knowledge_timestamp_remains_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].knowledge_timestamp = null;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.knowledge_timestamp, null);
});

test('test_zero_weight_not_converted_to_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].weight = 0.0;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.weight, 0.0);
});

test('test_zero_contribution_not_converted_to_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].contribution = 0.0;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.contribution, 0.0);
});

test('test_false_passed_value_remains_false', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results[0].passed = false;
  const rule = adaptQxV2Evaluation(input).evidence.find(item => item.key === 'QX-TRIG-002');

  assert.equal(rule.ruleResult.passed, false);
});

test('test_exact_duplicate_rule_result_is_deduplicated', () => {
  const input = triggerRulePayload();
  const duplicate = {...input.trigger.trigger_event.rule_results[0]};
  input.trigger.trigger_event.rule_results.push(duplicate);

  const rules = adaptQxV2Evaluation(input).evidence
    .filter(item => item.type === 'RULE_RESULT' && item.key === 'QX-TRIG-002');

  assert.equal(rules.length, 1);
});

test('test_same_rule_id_with_different_timestamps_is_not_deduplicated', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results.push({
    ...input.trigger.trigger_event.rule_results[0],
    observed_value: 452.5,
    event_timestamp: '2026-09-16T14:05:00Z',
  });

  const rules = adaptQxV2Evaluation(input).evidence
    .filter(item => item.type === 'RULE_RESULT' && item.key === 'QX-TRIG-002');

  assert.equal(rules.length, 2);
  assert.deepEqual(rules.map(item => item.ruleResult.observed_value), [451.25, 452.5]);
});

test('test_dedupe_distinguishes_empty_string_event_timestamp_from_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results = [
    {...input.trigger.trigger_event.rule_results[0], event_timestamp: ''},
    {...input.trigger.trigger_event.rule_results[0], event_timestamp: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
  assert.deepEqual(rules.map(item => item.ruleResult.event_timestamp), ['', null]);
});

test('test_dedupe_distinguishes_empty_string_knowledge_timestamp_from_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results = [
    {...input.trigger.trigger_event.rule_results[0], knowledge_timestamp: ''},
    {...input.trigger.trigger_event.rule_results[0], knowledge_timestamp: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
  assert.deepEqual(rules.map(item => item.ruleResult.knowledge_timestamp), ['', null]);
});

test('test_dedupe_distinguishes_zero_from_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results = [
    {...input.trigger.trigger_event.rule_results[0], event_timestamp: 0},
    {...input.trigger.trigger_event.rule_results[0], event_timestamp: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
  assert.deepEqual(rules.map(item => item.ruleResult.event_timestamp), [0, null]);
});

test('test_dedupe_distinguishes_false_from_null', () => {
  const input = triggerRulePayload();
  input.trigger.trigger_event.rule_results = [
    {...input.trigger.trigger_event.rule_results[0], knowledge_timestamp: false},
    {...input.trigger.trigger_event.rule_results[0], knowledge_timestamp: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
  assert.deepEqual(rules.map(item => item.ruleResult.knowledge_timestamp), [false, null]);
});

test('undefined rule_version differs from null in dedupe identity', () => {
  const input = triggerRulePayload();
  const withoutVersion = {...input.trigger.trigger_event.rule_results[0]};
  delete withoutVersion.rule_version;
  input.trigger.trigger_event.rule_results = [
    withoutVersion,
    {...input.trigger.trigger_event.rule_results[0], rule_version: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
});

test('undefined event_timestamp differs from null in dedupe identity', () => {
  const input = triggerRulePayload();
  const withoutTimestamp = {...input.trigger.trigger_event.rule_results[0]};
  delete withoutTimestamp.event_timestamp;
  input.trigger.trigger_event.rule_results = [
    withoutTimestamp,
    {...input.trigger.trigger_event.rule_results[0], event_timestamp: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
});

test('undefined knowledge_timestamp differs from null in dedupe identity', () => {
  const input = triggerRulePayload();
  const withoutTimestamp = {...input.trigger.trigger_event.rule_results[0]};
  delete withoutTimestamp.knowledge_timestamp;
  input.trigger.trigger_event.rule_results = [
    withoutTimestamp,
    {...input.trigger.trigger_event.rule_results[0], knowledge_timestamp: null},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
});

test('empty string differs from undefined in dedupe identity', () => {
  const input = triggerRulePayload();
  const withoutTimestamp = {...input.trigger.trigger_event.rule_results[0]};
  delete withoutTimestamp.event_timestamp;
  input.trigger.trigger_event.rule_results = [
    withoutTimestamp,
    {...input.trigger.trigger_event.rule_results[0], event_timestamp: ''},
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
});

test('exact duplicate with undefined identity values is deduplicated', () => {
  const input = triggerRulePayload();
  const incompleteRule = {...input.trigger.trigger_event.rule_results[0]};
  delete incompleteRule.rule_version;
  delete incompleteRule.event_timestamp;
  delete incompleteRule.knowledge_timestamp;
  input.trigger.trigger_event.rule_results = [incompleteRule, {...incompleteRule}];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 1);
});

test('null and undefined observations do not collapse', () => {
  const input = triggerRulePayload();
  const undefinedObservation = {...input.trigger.trigger_event.rule_results[0]};
  delete undefinedObservation.rule_version;
  delete undefinedObservation.event_timestamp;
  delete undefinedObservation.knowledge_timestamp;
  input.trigger.trigger_event.rule_results = [
    undefinedObservation,
    {
      ...input.trigger.trigger_event.rule_results[0],
      rule_version: null,
      event_timestamp: null,
      knowledge_timestamp: null,
    },
  ];

  const rules = adaptQxV2Evaluation(input).evidence.filter(item => item.type === 'RULE_RESULT');

  assert.equal(rules.length, 2);
});

test('test_blocked_trigger_stage_maps_to_blocked', () => {
  const input = payload('BLOCKED');
  input.trigger = {state: 'NO_SETUP', publication_state: 'BLOCKED'};

  assert.equal(
    adaptQxV2Evaluation(input).stageAvailability.find(stage => stage.key === 'trigger').status,
    'BLOCKED',
  );
});

test('test_skipped_trigger_stage_maps_to_skipped', () => {
  const input = payload('NO_SETUP');
  input.stage_latencies.trigger_ms = 'SKIPPED';

  assert.equal(
    adaptQxV2Evaluation(input).stageAvailability.find(stage => stage.key === 'trigger').status,
    'SKIPPED',
  );
});

test('test_successful_trigger_stage_maps_to_available', () => {
  const input = triggerRulePayload();
  input.stage_latencies.trigger_ms = 0.84;

  assert.equal(
    adaptQxV2Evaluation(input).stageAvailability.find(stage => stage.key === 'trigger').status,
    'AVAILABLE',
  );
});

test('test_non_null_blocked_payload_not_mapped_available', () => {
  const input = payload('BLOCKED');
  input.trigger = {state: 'NO_SETUP', publication_state: 'BLOCKED', evidence_ladder: {reason: 'BLOCKED'}};
  input.stage_latencies.trigger_ms = 0.21;

  assert.notEqual(
    adaptQxV2Evaluation(input).stageAvailability.find(stage => stage.key === 'trigger').status,
    'AVAILABLE',
  );
});

test('blocked playbook array maps the playbooks stage to blocked', () => {
  const input = payload('BLOCKED');
  input.playbooks = [{state: 'NO_SETUP', publication_state: 'BLOCKED'}];
  input.stage_latencies.playbooks_ms = 0.65;

  const playbooks = adaptQxV2Evaluation(input).stageAvailability
    .find(stage => stage.key === 'playbooks');

  assert.equal(playbooks.status, 'BLOCKED');
});

test('successfully evaluated playbook array remains available', () => {
  const input = payload('WATCH');
  input.playbooks = [{state: 'WATCH', publication_state: 'RESEARCH_ONLY'}];
  input.stage_latencies.playbooks_ms = 0.65;

  const playbooks = adaptQxV2Evaluation(input).stageAvailability
    .find(stage => stage.key === 'playbooks');

  assert.equal(playbooks.status, 'AVAILABLE');
});

test('adapter projects canonical lifecycle detail without recalculation', () => {
  const input = triggerRulePayload();
  input.evaluation_timestamp = '2026-09-16T14:05:00Z';
  input.timeframe = '15m';
  input.structure = {
    regime: 'BULLISH', structure_score: 74, latest_bos: 'BULLISH_BOS', latest_choch: null,
    latest_event: {event_type: 'BULLISH_BOS', event_timestamp: '2026-09-16T14:00:00Z', knowledge_timestamp: '2026-09-16T14:05:00Z'},
    protected_high: null, protected_low: {price: 445, knowledge_timestamp: '2026-09-16T13:55:00Z'},
  };
  input.market_regime = {
    trend: 'BULLISH', volatility: 'NORMAL', gamma: 'POSITIVE_GAMMA', session: 'OPENING',
  };
  input.primary_playbook_candidate.state = 'ARMED';
  input.primary_playbook_candidate.trigger_definition = 'Close above order block';
  input.primary_playbook_candidate.invalidation_source_type = 'ORDER_BLOCK_DISTAL';
  input.trigger.trigger_event.trigger_rule_type = 'CLOSE_ABOVE_LEVEL';
  input.trigger.trigger_event.event_timestamp = '2026-09-16T14:00:00Z';
  input.trigger.trigger_event.knowledge_timestamp = '2026-09-16T14:05:00Z';
  input.tradeability = {
    state: 'TRADEABLE', participation_score: 72, participation_evidence_coverage: 0.8,
    risk_reward_to_best_structural_target: 2.4, observed_entry_reference_price: 451.25,
    target_candidates: [463], reason_codes: ['TRADEABLE_ALL_GATES_PASS'],
  };
  input.options_expression = {
    state: 'SUITABLE', primary_candidate_id: 'candidate-1', data_as_of: '2026-09-16T14:04:00Z', publication_state: 'RESEARCH_ONLY', reason_codes: ['OPTIONS_EXPRESSION_SUITABLE'],
    candidate_strategies: [{
      candidate_id: 'candidate-1', strategy_type: 'CALL_DEBIT_SPREAD', expiration: '2026-10-16',
      max_loss: 240, max_profit: 510,
    }],
  };
  input.portfolio_risk = {
    state: 'PORTFOLIO_APPROVED', binding_constraint: 'MAX_RISK', approved_contracts_cap: 2,
    data_as_of: '2026-09-16T14:04:30Z', evidence_ladder: {account_snapshot: 'PARTIAL'}, reason_codes: ['PORTFOLIO_RISK_APPROVED'],
  };

  const view = adaptQxV2Evaluation(input);

  assert.deepEqual(view.marketRegime, {
    trend: 'BULLISH', volatility: 'NORMAL', gamma: 'POSITIVE_GAMMA', session: 'OPENING',
  });
  assert.equal(view.timeframe, '15m');
  assert.equal(view.structureSummary.latestBos, 'BULLISH_BOS');
  assert.equal(view.structureSummary.protectedLow, 445);
  assert.equal(view.playbookState, 'ARMED');
  assert.equal(view.triggerCondition, 'CLOSE_ABOVE_LEVEL');
  assert.equal(view.triggerEventTimestamp, '2026-09-16T14:00:00Z');
  assert.equal(view.triggerKnowledgeTimestamp, '2026-09-16T14:05:00Z');
  assert.equal(view.invalidationCondition, 'ORDER_BLOCK_DISTAL');
  assert.deepEqual(view.tradeabilitySummary, {
    state: 'TRADEABLE', participationScore: 72, participationCoverage: 0.8, structuralRiskReward: 2.4,
    observedEntryReference: 451.25, targetCandidates: [463], reasonCodes: ['TRADEABLE_ALL_GATES_PASS'],
  });
  assert.deepEqual(view.optionsSummary, {
    state: 'SUITABLE', candidateCount: 1, strategyType: 'CALL_DEBIT_SPREAD',
    expiration: '2026-10-16', maxLoss: 240, maxProfit: 510,
    dataAsOf: '2026-09-16T14:04:00Z', publicationState: 'RESEARCH_ONLY', reasonCodes: ['OPTIONS_EXPRESSION_SUITABLE'],
  });
  assert.deepEqual(view.portfolioSummary, {
    state: 'PORTFOLIO_APPROVED', bindingConstraint: 'MAX_RISK', approvedContractsCap: 2,
    dataAsOf: '2026-09-16T14:04:30Z', publicationState: null, evidenceStatus: 'PARTIAL', reasonCodes: ['PORTFOLIO_RISK_APPROVED'],
  });
});
