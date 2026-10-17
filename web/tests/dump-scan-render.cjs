const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1100 } });
  await p.goto('http://127.0.0.1:8790/scanner', { waitUntil: 'networkidle' });
  await p.waitForTimeout(2500);
  await p.evaluate(() => {
    const base = { source:'schwab', quote_source:'schwab', score:50, entry:100, invalidation:95,
      target:110, risk_reward:2.0, atr:3, rsi:55, macd_hist:0.1, last:100, alerts:[] };
    window.SCAN = { rule_version:'TEST', timeframe:'1d', verdict:'OK', benchmark:'SPY',
      benchmark_source:'test', symbols:4, errors:0,
      results: [
        Object.assign({}, base, { symbol:'AAAL', side:'LONG', signal:'CALL_READY' }),
        Object.assign({}, base, { symbol:'BBBS', side:'SHORT', signal:'PUT_READY' }),
        Object.assign({}, base, { symbol:'CCCS', side:'SHORT', signal:'PUT_ACTIVE' }),
        Object.assign({}, base, { symbol:'DDDN', side:null, signal:'WAIT' }),
      ] };
    renderScan();
  });
  await p.waitForTimeout(600);
  const txt = await p.locator('#results').innerText();
  console.log('---- ACTUAL RENDERED TEXT ----');
  console.log(txt);
  console.log('---- END ----');
  await b.close();
})();
