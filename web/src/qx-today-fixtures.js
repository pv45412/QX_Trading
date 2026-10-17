import {createCanonicalOpportunityFixtures} from './qx-opportunities-fixtures.js';
import {createQxV2PreviewFixture} from './qx-v2-fixtures.js';

export const todayFixtureStates = ['armed', 'triggered', 'no_opportunities', 'market_blocked', 'partial_positions'];

export function createTodayFixture(state = 'armed', horizon = 'DAY') {
  const normalizedState = todayFixtureStates.includes(state) ? state : 'armed';
  const timeframe = horizon === 'SWING' ? '1h' : horizon === 'INVEST' ? '1d' : '5m';
  const spy = createQxV2PreviewFixture(normalizedState === 'market_blocked' ? 'BLOCKED' : 'WATCH', 'SPY');
  const qqq = createQxV2PreviewFixture('WATCH', 'QQQ');
  spy.timeframe = timeframe;
  qqq.timeframe = timeframe;
  const opportunities = createCanonicalOpportunityFixtures(horizon);
  const selectedStates = normalizedState === 'triggered'
    ? new Set(['TRIGGERED', 'ARMED', 'WATCH'])
    : normalizedState === 'armed' || normalizedState === 'partial_positions'
      ? new Set(['ARMED', 'WATCH'])
      : new Set();
  return {
    evaluations: {
      SPY: {data: spy, error: ''},
      QQQ: {data: qqq, error: ''},
    },
    opportunities: opportunities.filter(row => selectedStates.has(row.state)),
    positionAttention: normalizedState === 'partial_positions'
      ? {status: 'PARTIAL', detail: 'Canonical account evidence is partial. Position-level attention is not published.'}
      : {status: 'UNAVAILABLE', detail: 'No approved canonical position-attention feed is available.'},
    healthItems: normalizedState === 'market_blocked'
      ? [{code: 'CANONICAL_PIPELINE_BLOCKED', label: 'SPY canonical pipeline blocked', detail: 'BLOCKED_PUBLICATION_STATE', destination: 'system'}]
      : [],
    legacyPayload: {rows: [{
      etf: 'AMD',
      name: 'Advanced Micro Devices',
      sector: 'Information Technology',
      as_of: '2026-09-16T14:35:00Z',
      return_1d: 0.024,
      excess_1d: 0.013,
      source: 'fixture_verified_mover',
    }]},
  };
}
