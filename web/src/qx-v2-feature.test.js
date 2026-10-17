import test from 'node:test';
import assert from 'node:assert/strict';

import {isQxOpportunitiesFixtureEnabled, isQxPortfolioFixtureEnabled, isQxResearchFixtureEnabled, isQxSystemFixtureEnabled, isQxTodayFixtureEnabled, isQxV2UiEnabled} from './qx-v2-feature.js';

test('runtime feature flag takes precedence', () => {
  assert.equal(
    isQxV2UiEnabled({qx_v2_ui_enabled: false}, {VITE_QX_V2_UI_ENABLED: 'true'}),
    false,
  );
  assert.equal(isQxV2UiEnabled({qx_v2_ui_enabled: true}, {}), true);
});

test('environment feature flag defaults safely off', () => {
  assert.equal(isQxV2UiEnabled(undefined, {VITE_QX_V2_UI_ENABLED: 'true'}), true);
  assert.equal(isQxV2UiEnabled(undefined, {}), false);
});

test('Opportunities fixtures require an explicit runtime flag', () => {
  assert.equal(isQxOpportunitiesFixtureEnabled(), false);
  assert.equal(isQxOpportunitiesFixtureEnabled({qx_opportunities_fixture_enabled: false}), false);
  assert.equal(isQxOpportunitiesFixtureEnabled({qx_opportunities_fixture_enabled: true}), true);
});

test('Today fixtures require an explicit runtime flag', () => {
  assert.equal(isQxTodayFixtureEnabled(), false);
  assert.equal(isQxTodayFixtureEnabled({qx_today_fixture_enabled: false}), false);
  assert.equal(isQxTodayFixtureEnabled({qx_today_fixture_enabled: true}), true);
});

test('Portfolio fixtures require an explicit runtime flag', () => {
  assert.equal(isQxPortfolioFixtureEnabled(), false);
  assert.equal(isQxPortfolioFixtureEnabled({qx_portfolio_fixture_enabled: false}), false);
  assert.equal(isQxPortfolioFixtureEnabled({qx_portfolio_fixture_enabled: true}), true);
});

test('Research fixtures require an explicit runtime flag', () => {
  assert.equal(isQxResearchFixtureEnabled(), false);
  assert.equal(isQxResearchFixtureEnabled({qx_research_fixture_enabled: false}), false);
  assert.equal(isQxResearchFixtureEnabled({qx_research_fixture_enabled: true}), true);
});

test('System fixtures require an explicit runtime flag', () => {
  assert.equal(isQxSystemFixtureEnabled(), false);
  assert.equal(isQxSystemFixtureEnabled({qx_system_fixture_enabled: false}), false);
  assert.equal(isQxSystemFixtureEnabled({qx_system_fixture_enabled: true}), true);
});
