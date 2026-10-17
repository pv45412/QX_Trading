const {chromium} = require('../../../../web/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');

const baseUrl = 'http://127.0.0.1:5177';
const output = __dirname;

(async () => {
  const browser = await chromium.launch({headless: true});
  const consoleErrors = [];
  const cases = [
    ['today-desktop-final.png', 1440, 900, '/?page=today&horizon=DAY&timeframe=5m', false, 'What Matters Now?'],
    ['today-mobile-final.png', 390, 844, '/?page=today&horizon=DAY&timeframe=5m', false, 'What Matters Now?'],
    ['opportunities-desktop-final.png', 1440, 900, '/?page=opportunities&horizon=DAY&timeframe=5m', false, 'Opportunities'],
    ['opportunities-mobile-final.png', 390, 844, '/?page=opportunities&horizon=DAY&timeframe=5m', false, 'Opportunities'],
    ['trade-desktop-final.png', 1440, 1000, '/?page=trade&symbol=SPY&horizon=DAY&timeframe=5m&fixture_state=ARMED', true, 'Trade Workspace'],
    ['trade-mobile-final.png', 390, 844, '/?page=trade&symbol=SPY&horizon=DAY&timeframe=5m&fixture_state=ARMED', true, 'Trade Workspace'],
  ];
  for (const [name, width, height, route, fixture, heading] of cases) {
    const page = await browser.newPage({viewport: {width, height}});
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(`${name}: ${message.text()}`);
    });
    if (fixture) {
      await page.addInitScript(() => {
        window.__QX_FEATURE_FLAGS__ = {qx_trade_fixture_enabled: true};
      });
    }
    await page.goto(`${baseUrl}${route}`, {waitUntil: 'domcontentloaded'});
    await page.locator('h1').filter({hasText: heading}).first().waitFor();
    await page.waitForTimeout(2500);
    await page.screenshot({path: path.join(output, name), fullPage: true});
    await page.close();
  }
  fs.writeFileSync(path.join(output, 'console-errors.txt'), consoleErrors.join('\n'));
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
