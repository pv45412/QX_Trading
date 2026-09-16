const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const baseUrl = process.env.QX_WEB_URL || 'http://127.0.0.1:5174';
const reportRoot = path.resolve(__dirname, '../../data/reports/ui_review');
const desktopDir = path.join(reportRoot, 'screenshots', 'desktop');
const responsiveDir = path.join(reportRoot, 'screenshots', 'responsive');
const traceDir = path.join(reportRoot, 'traces');
const videoDir = path.join(reportRoot, 'videos');
const videoTempDir = path.join(reportRoot, '.video-temp');
const journeysOnly = process.env.QX_UI_REVIEW_JOURNEYS_ONLY === '1';

const routedPages = [
  ['01-markets-relative-strength.png', 'relative_strength'],
  ['02-today-command-center.png', 'command_center'],
  ['03-today-morning-report.png', 'morning_report'],
  ['04-today-daily-workflow.png', 'daily_workflow'],
  ['05-markets-spx-nq-futures.png', 'spx_nq_futures'],
  ['06-markets-sector-rotation.png', 'sector_rotation'],
  ['07-scanner-scanner.png', 'scan'],
  ['08-scanner-broad-watchlist.png', 'broad_watchlist'],
  ['09-scanner-heatmap.png', 'heatmap'],
  ['10-research-ticker-history.png', 'ticker_history'],
  ['11-research-options-ideas.png', 'options_ideas'],
  ['12-research-options-flow.png', 'options_flow'],
  ['13-research-liquidity-map.png', 'liquidity_map'],
  ['14-research-backtest.png', 'backtest'],
  ['15-research-strategy-lab.png', 'strategy_lab'],
  ['16-journal-idea-tracking.png', 'idea_tracking'],
  ['17-journal-outcome-journal.png', 'journal'],
  ['18-system-data-cache.png', 'data_cache'],
  ['19-system-schwab-api.png', 'schwab'],
  ['20-system-jobs.png', 'jobs'],
  ['21-system-run-history.png', 'run_history'],
  ['22-system-strategy-rules.png', 'strategy_rules'],
];

const quickJumps = [
  ['23-quick-options-ideas-hub.png', 'options-ideas-hub'],
  ['24-quick-research-studio.png', 'research-studio'],
  ['25-quick-options-scanner.png', 'options-scanner-v1'],
  ['26-quick-spx-command.png', 'spx-dashboard'],
  ['27-quick-prompt-studio.png', 'daily-prompt'],
  ['28-quick-day-trader-terminal.png', 'qx-terminal'],
  ['29-quick-qx-suite.png', 'qx-suite'],
  ['30-quick-sector-ranking.png', 'ranking'],
  ['31-quick-market-movers.png', 'movers'],
  ['32-quick-ai-review.png', 'ai-review'],
  ['33-quick-holdings.png', 'holdings'],
];

const responsivePages = [
  ['today', '?page=command_center', null],
  ['scanner', '?page=scan', null],
  ['day-trader-terminal', '?page=command_center', 'qx-terminal'],
  ['holdings-portfolio', '?page=relative_strength', 'holdings'],
  ['research', '?page=ticker_history', 'research-studio'],
  ['system', '?page=schwab', null],
];

const viewports = [
  ['desktop', {width: 1440, height: 1000}],
  ['laptop', {width: 1280, height: 800}],
  ['mobile', {width: 390, height: 844}],
];

const lifecycleStates = [
  'NO_SETUP',
  'WATCH',
  'ARMED',
  'TRIGGERED',
  'TRADEABLE',
  'BLOCKED',
  'PORTFOLIO_VETOED',
  'PORTFOLIO_APPROVED',
];

let reviewAsOf = '';

function resetOutput() {
  const directories = journeysOnly
    ? [traceDir, videoDir, videoTempDir]
    : [desktopDir, responsiveDir, traceDir, videoDir, videoTempDir];
  for (const directory of directories) {
    fs.rmSync(directory, {recursive: true, force: true});
    fs.mkdirSync(directory, {recursive: true});
  }
}

async function tourCurrentSurface(page) {
  for (let index = 0; index < 24; index += 1) {
    const direction = index < 12 ? 1 : -1;
    await page.mouse.wheel(0, direction * Math.round(page.viewportSize().height * 0.72));
    await page.waitForTimeout(5000);
  }
}

async function preparePage(page) {
  await page.locator('.qx-app-shell, .qx-v2-preview-shell').first().waitFor({timeout: 30000});
  const preloader = page.locator('.qx-preloader-overlay');
  if (await preloader.count()) {
    await preloader.waitFor({state: 'hidden', timeout: 15000}).catch(() => {});
  }
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    for (const input of document.querySelectorAll('input[type="password"]')) input.value = '';
    for (const input of document.querySelectorAll('input[autocomplete="new-password"]')) input.value = '';
  });
  await page.addStyleTag({content: 'input[type="password"]{color:transparent!important;text-shadow:none!important}'});
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
}

async function configureContext(context) {
  await context.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
      const method = String(init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
      if (method !== 'GET') {
        const requestUrl = new URL(typeof input === 'string' ? input : input.url, window.location.href);
        if (requestUrl.pathname.startsWith('/api/position-advisor')) {
          return Promise.resolve(new Response('{"detail":"Unavailable during read-only UI review."}', {
            status: 503,
            headers: {'Content-Type': 'application/json'},
          }));
        }
        return Promise.resolve(new Response('{}', {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }));
      }
      return nativeFetch(input, init);
    };
  });
  await context.route('**/api/**', async route => {
    const request = route.request();
    if (request.method() === 'GET') return route.fallback();
    return route.fulfill({status: 200, contentType: 'application/json', body: '{}'});
  });
  await context.route('**/api/system/schwab/credentials/status', async route => {
    try {
      const response = await route.fetch();
      const status = await response.json();
      status.client_id_last4 = null;
      await route.fulfill({response, json: status});
    } catch {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          configured: false,
          client_id_last4: null,
          redirect_uri: 'https://127.0.0.1',
          oauth_status: 'UNAVAILABLE',
          refresh_token_status: 'UNAVAILABLE',
          provider_health: 'UNAVAILABLE',
          last_verified_at: null,
        }),
      });
    }
  });
}

function reviewSuffix(suffix) {
  if (!reviewAsOf || !suffix.startsWith('?')) return suffix;
  const params = new URLSearchParams(suffix.slice(1));
  const page = params.get('page') || 'relative_strength';
  if (page === 'relative_strength' || page === 'sector_rotation') params.set('as_of', reviewAsOf);
  return `?${params.toString()}`;
}

async function openApp(page, suffix) {
  await page.goto(`${baseUrl}/${reviewSuffix(suffix)}`, {waitUntil: 'domcontentloaded', timeout: 45000});
  await preparePage(page);
}

function observePage(page, bucket, nonGetRequests) {
  page.on('pageerror', error => bucket.push({type: 'pageerror', message: error.message}));
  page.on('console', message => {
    if (message.type() === 'error') bucket.push({type: 'console', message: message.text()});
  });
  page.on('request', request => {
    if (request.method() !== 'GET') {
      nonGetRequests.push({method: request.method(), path: new URL(request.url()).pathname});
    }
  });
}

async function captureDesktop(browser, results) {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  await configureContext(context);
  const page = await context.newPage();
  observePage(page, results.browser_errors, results.non_get_requests);
  try {
    for (const [filename, route] of routedPages) {
      try {
        await openApp(page, `?page=${route}&etf=XLK&symbol=MSFT`);
        await page.screenshot({path: path.join(desktopDir, filename), fullPage: true});
        results.desktop.push({filename, route, status: 'CAPTURED'});
      } catch (error) {
        results.desktop.push({filename, route, status: 'FAILED', reason: error.message});
      }
    }

    await openApp(page, '?page=relative_strength&etf=XLK&symbol=MSFT');
    for (const [filename, anchor] of quickJumps) {
      const target = page.locator(`#${anchor}`);
      if (await target.count()) {
        await target.first().scrollIntoViewIfNeeded();
        await page.waitForTimeout(350);
        await page.screenshot({path: path.join(desktopDir, filename)});
        results.quick_jumps.push({filename, anchor, status: 'CAPTURED'});
      } else {
        results.quick_jumps.push({filename, anchor, status: 'MISSING'});
      }
    }
  } finally {
    await context.close();
  }
}

async function captureResponsive(browser, results) {
  for (const [viewportName, viewport] of viewports) {
    const context = await browser.newContext({viewport});
    await configureContext(context);
    const page = await context.newPage();
    observePage(page, results.browser_errors, results.non_get_requests);
    try {
      for (const [name, suffix, anchor] of responsivePages) {
        const filename = `${name}-${viewportName}.png`;
        try {
          await openApp(page, `${suffix}&etf=XLK&symbol=MSFT`);
          if (anchor) {
            const target = page.locator(`#${anchor}`);
            const attached = await target.first().waitFor({state: 'attached', timeout: 12000}).then(() => true).catch(() => false);
            if (!attached) {
              results.responsive.push({filename, viewport: viewportName, status: 'MISSING', anchor});
              continue;
            }
            await target.first().scrollIntoViewIfNeeded();
            await page.waitForTimeout(350);
          }
          await page.screenshot({path: path.join(responsiveDir, filename)});
          results.responsive.push({filename, viewport: viewportName, status: 'CAPTURED'});
        } catch (error) {
          results.responsive.push({filename, viewport: viewportName, status: 'FAILED', reason: error.message});
        }
      }
    } finally {
      await context.close();
    }
  }
}

async function captureLifecycle(browser, results) {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  await configureContext(context);
  await context.addInitScript(() => { window.__QX_FEATURE_FLAGS__ = {qx_v2_ui_enabled: true}; });
  const page = await context.newPage();
  observePage(page, results.browser_errors, results.non_get_requests);
  try {
    for (let index = 0; index < lifecycleStates.length; index += 1) {
      const state = lifecycleStates[index];
      const prefix = `lifecycle-${String(index + 1).padStart(2, '0')}-${state.toLowerCase().replaceAll('_', '-')}`;
      await openApp(page, `qx-v2-preview.html?state=${state}`);
      await page.getByText('TEST / PREVIEW DATA — NOT LIVE', {exact: true}).waitFor();
      await page.locator('.qx-lifecycle-current .qx-state').filter({hasText: state}).waitFor();
      await page.screenshot({path: path.join(desktopDir, `${prefix}-collapsed.png`), fullPage: true});
      const why = page.locator('.qx-lifecycle-why');
      if (!(await why.getAttribute('open'))) await why.locator('summary').click();
      await page.screenshot({path: path.join(desktopDir, `${prefix}-why-expanded.png`), fullPage: true});
      results.lifecycle.push({state, collapsed: `${prefix}-collapsed.png`, expanded: `${prefix}-why-expanded.png`, fixture: true});
    }
  } finally {
    await context.close();
  }
}

async function recordJourney(browser, name, runner, results) {
  const context = await browser.newContext({
    viewport: {width: 1440, height: 1000},
    recordVideo: {dir: videoTempDir, size: {width: 1440, height: 1000}},
  });
  await configureContext(context);
  await context.tracing.start({screenshots: true, snapshots: true, sources: true});
  const page = await context.newPage();
  const errors = [];
  observePage(page, errors, results.non_get_requests);
  const outcome = {name, status: 'COMPLETED', steps: [], breaks: [], errors};
  try {
    await runner(page, outcome);
  } catch (error) {
    outcome.status = 'BROKEN';
    outcome.breaks.push(error.message);
  }
  const tracePath = path.join(traceDir, `${name}.zip`);
  await context.tracing.stop({path: tracePath});
  const video = page.video();
  await page.close();
  if (video) await video.saveAs(path.join(videoDir, `${name}.webm`));
  await context.close();
  if (outcome.breaks.length) outcome.status = 'BROKEN';
  results.journeys.push(outcome);
}

async function runJourneys(browser, results) {
  await recordJourney(browser, 'day_trader', async (page, outcome) => {
    await openApp(page, '?page=command_center&symbol=SPY&etf=XLK');
    outcome.steps.push('Opened Today / Command Center.');
    const terminal = page.locator('#qx-terminal');
    await terminal.scrollIntoViewIfNeeded();
    outcome.steps.push('Opened Day Trader Terminal.');
    const ticker = terminal.locator('.ticker-chip').first();
    if (await ticker.count()) {
      await ticker.click();
      await page.waitForTimeout(900);
      outcome.steps.push('Selected the first available terminal symbol and inspected its legacy signal detail.');
    } else {
      outcome.breaks.push('No terminal opportunity was available in the current loaded watchlist.');
    }
    if (await page.locator('[aria-label="Canonical QX lifecycle"]').count()) {
      outcome.steps.push('Inspected canonical lifecycle state.');
    } else {
      outcome.breaks.push('The current Today/Terminal workspace has no linked canonical QX lifecycle or WHY panel.');
    }
    await tourCurrentSurface(page);
  }, results);

  await recordJourney(browser, 'swing_trader', async (page, outcome) => {
    await openApp(page, '?page=scan&symbol=MSFT&etf=XLK');
    outcome.steps.push('Opened Scanner workspace.');
    const candidate = page.locator('.qx-candidate-list-card tbody tr').first();
    if (await candidate.count()) {
      await candidate.click();
      await page.waitForTimeout(700);
      outcome.steps.push('Selected the first available scanner candidate.');
      if (await page.locator('.qx-inspector-card').count()) outcome.steps.push('Inspected legacy setup, R:R, option fit, and factor evidence.');
    } else {
      outcome.breaks.push('No scanner candidate was available in the current loaded data.');
    }
    if (!(await page.locator('[aria-label="Canonical QX lifecycle"]').count())) {
      outcome.breaks.push('Scanner detail is not connected to canonical lifecycle, higher-timeframe evidence, or portfolio-risk stages.');
    }
    await tourCurrentSurface(page);
  }, results);

  await recordJourney(browser, 'long_term_investor', async (page, outcome) => {
    await openApp(page, '?page=relative_strength&symbol=MSFT&etf=XLK');
    outcome.steps.push('Opened Markets / Relative Strength workspace.');
    const holdings = page.locator('#holdings');
    if (await holdings.count()) {
      await holdings.scrollIntoViewIfNeeded();
      await page.waitForTimeout(600);
      outcome.steps.push('Inspected ETF holdings and concentration view.');
    } else {
      outcome.breaks.push('Holdings were unavailable because no selected ETF detail loaded.');
    }
    const research = page.locator('#research-studio');
    if (await research.count()) {
      await research.scrollIntoViewIfNeeded();
      outcome.steps.push('Inspected the current symbol-research entry surface without submitting analysis.');
    }
    outcome.breaks.push('Holdings are ETF composition data, not a broker portfolio; no linked long-term position-risk and thesis journey exists.');
    await tourCurrentSurface(page);
  }, results);
}

(async () => {
  resetOutput();
  try {
    const response = await fetch(`${baseUrl}/api/rotation/analytics`);
    const analytics = response.ok ? await response.json() : null;
    reviewAsOf = String(analytics?.benchmark_metrics?.as_of || '').slice(0, 10);
  } catch {
    reviewAsOf = '';
  }
  const existingResults = journeysOnly && fs.existsSync(path.join(reportRoot, 'capture_results.json'))
    ? JSON.parse(fs.readFileSync(path.join(reportRoot, 'capture_results.json'), 'utf8'))
    : {};
  const results = {
    ...existingResults,
    generated_at: new Date().toISOString(),
    base_url: baseUrl,
    read_only: true,
    sensitive_status_fields_redacted: true,
    review_as_of: reviewAsOf || null,
    desktop: existingResults.desktop || [],
    quick_jumps: existingResults.quick_jumps || [],
    responsive: existingResults.responsive || [],
    lifecycle: existingResults.lifecycle || [],
    journeys: [],
    browser_errors: [],
    non_get_requests: [],
  };
  const browser = await chromium.launch({headless: true});
  try {
    if (!journeysOnly) {
      await captureDesktop(browser, results);
      await captureResponsive(browser, results);
      await captureLifecycle(browser, results);
    }
    await runJourneys(browser, results);
  } finally {
    await browser.close();
    fs.rmSync(videoTempDir, {recursive: true, force: true});
  }
  fs.writeFileSync(path.join(reportRoot, 'capture_results.json'), `${JSON.stringify(results, null, 2)}\n`);

  const failures = [
    ...results.desktop.filter(item => item.status === 'FAILED'),
    ...results.responsive.filter(item => item.status === 'FAILED'),
  ];
  if (failures.length || results.non_get_requests.length) process.exitCode = 1;
})().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
