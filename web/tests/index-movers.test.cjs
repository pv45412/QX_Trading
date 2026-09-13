const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
for(const width of [1440,390]) test(`index and sector movers ${width}`,async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width,height:1000}});
  await page.route('**/api/rotation/*/holdings',r=>r.fulfill({status:503,body:'{}'}));
  await page.goto('http://127.0.0.1:5173/');
  await page.getByLabel('Movers universe').selectOption('sp100');
  await page.locator('#movers tbody tr').first().waitFor();
  await page.getByLabel('Movers sector').selectOption('Information Technology');
  const cells=await page.locator('#movers tbody .ticker small').allTextContents();
  assert.ok(cells.length>0);
  assert.ok(cells.every(x=>x==='Information Technology'));
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#movers').scrollIntoViewIfNeeded();
  await page.screenshot({path:`tests/index-movers-${width}.png`});
 } finally {await browser.close();}
});
