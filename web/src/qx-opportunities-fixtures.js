import {canonicalOpportunityFromEvaluation} from './qx-opportunities-model.js';
import {createQxV2PreviewFixture} from './qx-v2-fixtures.js';

const fixtureStates = [
  'ARMED',
  'TRIGGERED',
  'TRADEABLE',
  'OPTIONS_NOT_SUITABLE',
  'PORTFOLIO_VETOED',
  'PORTFOLIO_APPROVED',
  'WATCH',
  'BLOCKED',
  'NO_SETUP',
];

const symbols = ['SPY', 'QQQ', 'NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMD', 'JPM', 'XOM'];
const timeframes = {DAY: '5m', SWING: '1h', INVEST: '1d'};

export function createCanonicalOpportunityFixtures(horizon = 'DAY') {
  const timeframe = timeframes[horizon] || timeframes.DAY;
  return fixtureStates.map((state, index) => {
    const payload = createQxV2PreviewFixture(state, symbols[index]);
    payload.timeframe = timeframe;
    payload.evaluation_id = `fixture-${horizon.toLowerCase()}-${state.toLowerCase()}-${symbols[index].toLowerCase()}`;
    return canonicalOpportunityFromEvaluation(payload, {horizon, fixtureState: state});
  });
}
