import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const {chromium} = await import(pathToFileURL(path.resolve('web/node_modules/playwright/index.mjs')).href);

const baseUrl = process.env.QX_WEB_URL || 'http://127.0.0.1:5174';
const reportDir = path.resolve('data/reports/front_half_review');
const screenshotDir = path.join(reportDir, 'screenshots');
const traceDir = path.join(reportDir, 'traces');
const videoDir = path.join(reportDir, 'videos');
const fixtureTimestamp = '2026-09-16T14:35:00Z';

for (const directory of [screenshotDir, traceDir, videoDir]) {
  fs.mkdirSync(directory, {recursive: true});
}

const moversPayload = {rows: [
  {etf: 'AMD', name: 'Advanced Micro Devices', sector: 'Information Technology', as_of: fixtureTimestamp, return_1d: 0.024, excess_1d: 0.013, source: 'schwab'},
  {etf: 'JPM', name: 'JPMorgan Chase', sector: 'Financials', as_of: fixtureTimestamp, return_1d: -0.004, excess_1d: -0.011, source: 'schwab'},
]};

const browser = await chromium.launch({headless: true});
const fixtureModule = await import(pathToFileURL(path.resolve('web/src/qx-v2-fixtures.js')).href);

async function configurePage(page) {
  await page.addInitScript(() => {
    window.__QX_FEATURE_FLAGS__ = {
      qx_today_fixture_enabled: true,
      qx_opportunities_fixture_enabled: true,
      qx_trade_fixture_enabled: true,
    };
  });
  await page.route('**/api/v2/qx/evaluate/**', route => {
    const symbol = new URL(route.request().url()).pathname.split('/').pop();
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(fixtureModule.createQxV2PreviewFixture('WATCH', symbol)),
    });
  });
  await page.route('**/api/ops/health', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({status: 'OK', components: []}),
  }));
  await page.route('**/api/movers/sp500', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(moversPayload),
  }));
}

async function capture(url, filename, viewport) {
  const context = await browser.newContext({viewport});
  const page = await context.newPage();
  await configurePage(page);
  await page.goto(`${baseUrl}/${url}`);
  await page.locator('h1').first().waitFor();
  await page.screenshot({path: path.join(screenshotDir, filename), fullPage: true});
  await context.close();
}

const viewports = {
  desktop: {width: 1920, height: 945},
  laptop: {width: 1440, height: 900},
  mobile: {width: 390, height: 844},
};

for (const [label, viewport] of Object.entries(viewports)) {
  await capture(`?page=today&horizon=DAY&timeframe=5m&today_state=triggered`, `today-${label}.png`, viewport);
  await capture(`?page=opportunities&horizon=DAY&timeframe=5m`, `opportunities-${label}.png`, viewport);
  await capture(`?page=trade&symbol=QQQ&horizon=DAY&timeframe=5m&evaluation_timestamp=${encodeURIComponent(fixtureTimestamp)}&evaluation_id=fixture-day-portfolio_vetoed-qqq&fixture_state=PORTFOLIO_VETOED`, `trade-${label}.png`, viewport);
}

for (const [state, filename] of [
  ['ARMED', 'trade-armed.png'],
  ['TRIGGERED', 'trade-triggered.png'],
  ['BLOCKED', 'trade-blocked.png'],
  ['PORTFOLIO_VETOED', 'trade-portfolio-vetoed.png'],
]) {
  await capture(`?page=trade&symbol=QQQ&horizon=DAY&timeframe=5m&evaluation_timestamp=${encodeURIComponent(fixtureTimestamp)}&evaluation_id=fixture-day-${state.toLowerCase()}-qqq&fixture_state=${state}`, filename, viewports.laptop);
}

for (const [state, filename] of [
  ['ARMED', 'trade-armed-why-expanded.png'],
  ['BLOCKED', 'trade-blocked-why-expanded.png'],
]) {
  const context = await browser.newContext({viewport: viewports.laptop});
  const page = await context.newPage();
  await configurePage(page);
  await page.goto(`${baseUrl}/?page=trade&symbol=QQQ&horizon=DAY&timeframe=5m&evaluation_timestamp=${encodeURIComponent(fixtureTimestamp)}&evaluation_id=fixture-day-${state.toLowerCase()}-qqq&fixture_state=${state}`);
  await page.locator('.qx-decision-title .qx-state').filter({hasText: state}).waitFor();
  await page.locator('.qx-lifecycle-why summary').click();
  await page.screenshot({path: path.join(screenshotDir, filename), fullPage: true});
  await context.close();
}

async function handoff(origin) {
  const context = await browser.newContext({viewport: viewports.laptop});
  const page = await context.newPage();
  await configurePage(page);
  if (origin === 'today') {
    await page.goto(`${baseUrl}/?page=today&horizon=SWING&timeframe=1h&today_state=triggered`);
    await page.getByRole('heading', {name: 'What Matters Now?'}).waitFor();
    const row = page.locator('.qx-today-opportunity').filter({hasText: 'TRIGGERED'}).first();
    const stateBefore = await row.locator('.qx-state').innerText();
    const href = await row.getByRole('link', {name: 'Open Trade'}).getAttribute('href');
    await row.getByRole('link', {name: 'Open Trade'}).click();
    await page.locator('.qx-decision-title .qx-state').filter({hasText: stateBefore}).waitFor();
    const result = await handoffResult(page, href, stateBefore);
    await context.close();
    return result;
  }
  await page.goto(`${baseUrl}/?page=opportunities&horizon=SWING&timeframe=1h`);
  await page.getByRole('heading', {name: 'Opportunities', exact: true}).waitFor();
  const row = page.locator('[data-source="canonical"]').filter({hasText: 'TRIGGERED'}).first();
  const stateBefore = await row.locator('.qx-state').innerText();
  const href = await row.getByRole('link', {name: 'Open Trade'}).getAttribute('href');
  await row.getByRole('link', {name: 'Open Trade'}).click();
  await page.locator('.qx-decision-title .qx-state').filter({hasText: stateBefore}).waitFor();
  const result = await handoffResult(page, href, stateBefore);
  await context.close();
  return result;
}

async function handoffResult(page, href, stateBefore) {
  const sourceUrl = new URL(href, baseUrl);
  const destinationUrl = new URL(page.url());
  const identity = page.getByLabel('Canonical evaluation identity');
  const fields = ['symbol', 'horizon', 'timeframe', 'evaluation_timestamp', 'evaluation_id'];
  const stable = Object.fromEntries(fields.map(field => [field, sourceUrl.searchParams.get(field) === destinationUrl.searchParams.get(field)]));
  return {
    source_href: sourceUrl.pathname + sourceUrl.search,
    destination_url: destinationUrl.pathname + destinationUrl.search,
    source_state: stateBefore,
    destination_state: await page.locator('.qx-decision-title .qx-state').innerText(),
    rendered_identity: await identity.innerText(),
    stable,
    passed: Object.values(stable).every(Boolean) && stateBefore === await page.locator('.qx-decision-title .qx-state').innerText(),
  };
}

const handoffTrace = {
  fixture_data: true,
  captured_at: new Date().toISOString(),
  today_to_trade: await handoff('today'),
  opportunities_to_trade: await handoff('opportunities'),
};
fs.writeFileSync(path.join(traceDir, 'context-handoff.json'), `${JSON.stringify(handoffTrace, null, 2)}\n`);

const journeyVideoPath = path.join(videoDir, 'front-half-user-journey.webm');
if (fs.existsSync(journeyVideoPath)) fs.rmSync(journeyVideoPath);
const journeyContext = await browser.newContext({
  viewport: viewports.laptop,
  recordVideo: {dir: videoDir, size: viewports.laptop},
});
await journeyContext.tracing.start({screenshots: true, snapshots: true, sources: true});
const journey = await journeyContext.newPage();
await configurePage(journey);

async function pause(seconds = 15) {
  await journey.waitForTimeout(seconds * 1000);
}

await journey.goto(`${baseUrl}/?page=today&horizon=SWING&timeframe=1h&today_state=triggered`);
await journey.getByRole('heading', {name: 'What Matters Now?'}).waitFor();
await pause();
await journey.getByRole('heading', {name: 'Market Pulse'}).scrollIntoViewIfNeeded();
await pause();
await journey.getByRole('heading', {name: 'Active QX Opportunities'}).scrollIntoViewIfNeeded();
await pause();
await journey.getByRole('link', {name: /View all opportunities/i}).click();
await journey.getByRole('heading', {name: 'Opportunities', exact: true}).waitFor();
await pause();
await journey.getByLabel('Opportunity filters').getByText('Lifecycle').locator('..').locator('select').selectOption('TRIGGERED');
await pause();
const opportunity = journey.locator('[data-source="canonical"]').filter({hasText: 'TRIGGERED'}).first();
await opportunity.scrollIntoViewIfNeeded();
await pause();
await opportunity.getByRole('link', {name: 'Open Trade'}).click();
await journey.getByRole('heading', {name: /Trade Workspace/}).waitFor();
await journey.locator('.qx-decision-title .qx-state').filter({hasText: 'TRIGGERED'}).waitFor();
await pause();
await journey.getByLabel('Canonical decision facts').scrollIntoViewIfNeeded();
await pause();
await journey.locator('.qx-lifecycle-panel').scrollIntoViewIfNeeded();
await pause();
await journey.locator('.qx-lifecycle-why summary').click();
await pause();
await journey.getByRole('heading', {name: 'Options Expression'}).scrollIntoViewIfNeeded();
await pause();
await journey.getByRole('heading', {name: 'Portfolio Risk'}).scrollIntoViewIfNeeded();
await pause();

await journeyContext.tracing.stop({path: path.join(traceDir, 'front-half-user-journey.zip')});
const recordedVideo = journey.video();
await journeyContext.close();
const recordedPath = await recordedVideo.path();
fs.renameSync(recordedPath, journeyVideoPath);
await browser.close();

console.log(JSON.stringify({
  screenshots: fs.readdirSync(screenshotDir).filter(name => name.endsWith('.png')).length,
  video: journeyVideoPath,
  trace: path.join(traceDir, 'front-half-user-journey.zip'),
  handoff: path.join(traceDir, 'context-handoff.json'),
}, null, 2));
