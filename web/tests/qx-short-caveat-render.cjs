// The live market has no SHORT signals today, so the scanner caveat cannot be
// exercised with real data. This injects a synthetic payload THROUGH the page's
// own module scope (via the scan-render path), to test the RENDERING logic.
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:8790';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));

  let pass = 0, fail = 0;
  const check = (name, ok, detail) => {
    if (ok) { pass++; console.log('  PASS ' + name + (detail ? ' :: ' + detail : '')); }
    else { fail++; console.log('  FAIL ' + name + (detail ? ' :: ' + detail : '')); }
  };

  // Intercept /api/scan and serve a payload containing SHORT rows.
  await page.route('**/api/scan*', async route => {
    const real = await route.fetch();
    const body = await real.json().catch(() => null);
    if (!body || !Array.isArray(body.results)) return route.fulfill({ response: real });

    const mk = (symbol, side, signal) => ({
      symbol, side, signal, source: 'schwab', quote_source: 'schwab', score: 60,
      entry: 100, invalidation: 95, target: 110, risk_reward: 2.0, atr: 3,
      rsi: 55, macd_hist: 0.1, last: 100, alerts: [],
      side_status: side === 'SHORT' ? 'UNPROVEN' : (side === 'LONG' ? 'MEASURED' : null),
      side_basis: side === 'SHORT' ? 'NEGATIVE_EXPECTANCY_MEASURED' : null,
      side_note: side === 'SHORT' ? 'test note' : null,
    });
    body.results = [
      mk('AAAL', 'LONG', 'CALL_READY'),
      mk('BBBS', 'SHORT', 'PUT_READY'),
      mk('CCCS', 'SHORT', 'PUT_ACTIVE'),
      mk('DDDN', null, 'WAIT'),
    ];
    await route.fulfill({ response: real, json: body });
  });

  console.log('=== SCANNER with injected SHORT rows ===');
  await page.goto(BASE + '/scanner', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3500);

  const text = await page.locator('#results').innerText().catch(() => '');
  console.log('--- rendered ---');
  console.log(text.split('\n').slice(0, 6).join('\n'));
  console.log('---------------');

  check('bearish heading says UNPROVEN', text.includes('BEARISH — UNPROVEN'),
        text.includes('BEARISH — UNPROVEN') ? 'found' : 'missing');
  check('bearish block counts 2', text.includes('BEARISH — UNPROVEN (2)'),
        text.includes('(2)') ? 'count correct' : 'wrong count');
  check('caveat cites -0.60 R', text.includes('-0.60'), text.includes('-0.60') ? 'shown' : 'missing');
  check('caveat cites +0.41 R', text.includes('+0.41'), text.includes('+0.41') ? 'shown' : 'missing');
  check('caveat explains market drift', text.includes('market drift'),
        text.includes('market drift') ? 'explained' : 'missing');
  check('caveat mentions the rejected gate', text.toLowerCase().includes('regime gate'),
        text.toLowerCase().includes('regime gate') ? 'mentioned' : 'missing');
  check('caveat says informational only', text.toLowerCase().includes('informational'),
        text.toLowerCase().includes('informational') ? 'stated' : 'missing');

  // The caveat banner sits BETWEEN the bullish and bearish blocks by design, so
  // scope the check to the bullish TABLE only: everything up to the banner.
  const bullSection = (text.split('UNPROVEN —')[0] || '');
  check('bullish block is NOT labelled unproven',
        !bullSection.toLowerCase().includes('unproven'),
        bullSection.toLowerCase().includes('unproven') ? 'leaked into bullish' : 'clean');
  check('bullish block present', bullSection.includes('BULLISH (1)'),
        bullSection.includes('BULLISH (1)') ? 'BULLISH (1)' : 'missing');
  check('not-qualified block present', text.includes('NOT QUALIFIED (1)'),
        text.includes('NOT QUALIFIED (1)') ? 'present' : 'missing');

  await page.screenshot({ path: 'C:/Project/2026/data/reports/qx_ui/short-caveat-scanner.png', fullPage: false });
  console.log('  screenshot: data/reports/qx_ui/short-caveat-scanner.png');

  check('no uncaught page errors', errors.length === 0, errors.length ? errors[0] : 'clean');
  console.log('\nRESULT: ' + pass + ' passed, ' + fail + ' failed');
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
