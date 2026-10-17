export function isQxV2UiEnabled(
  runtimeFlags = globalThis.__QX_FEATURE_FLAGS__,
  environment = import.meta.env,
) {
  if (typeof runtimeFlags?.qx_v2_ui_enabled === 'boolean') {
    return runtimeFlags.qx_v2_ui_enabled;
  }
  return String(environment?.VITE_QX_V2_UI_ENABLED || '').toLowerCase() === 'true';
}

export const qx_v2_ui_enabled = isQxV2UiEnabled();

export function isQxTradeFixtureEnabled(runtimeFlags = globalThis.__QX_FEATURE_FLAGS__) {
  return runtimeFlags?.qx_trade_fixture_enabled === true;
}

export function isQxOpportunitiesFixtureEnabled(runtimeFlags = globalThis.__QX_FEATURE_FLAGS__) {
  return runtimeFlags?.qx_opportunities_fixture_enabled === true;
}

export function isQxTodayFixtureEnabled(runtimeFlags = globalThis.__QX_FEATURE_FLAGS__) {
  return runtimeFlags?.qx_today_fixture_enabled === true;
}

export function isQxPortfolioFixtureEnabled(runtimeFlags = globalThis.__QX_FEATURE_FLAGS__) {
  return runtimeFlags?.qx_portfolio_fixture_enabled === true;
}

export function isQxResearchFixtureEnabled(runtimeFlags = globalThis.__QX_FEATURE_FLAGS__) {
  return runtimeFlags?.qx_research_fixture_enabled === true;
}

export function isQxSystemFixtureEnabled(runtimeFlags = globalThis.__QX_FEATURE_FLAGS__) {
  return runtimeFlags?.qx_system_fixture_enabled === true;
}
