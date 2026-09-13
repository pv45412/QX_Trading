const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');

// Local servers must be running. Holdings are stubbed to avoid provider traffic.
for(const width of [1440,768,390]) {
 test(`dashboard workflow and reload recovery at ${width}px`,async()=>{
  const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
  try {
   const page=await browser.newPage({viewport:{width,height:1000}});
   const errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/api/rotation/*/holdings',route=>route.fulfill({status:503,body:'{}'}));
   await page.goto('http://127.0.0.1:5173/?etf=XLE');
   await page.locator('.reference-ranking tbody tr').first().waitFor();
   await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
   const count=await page.locator('.reference-ranking tbody tr').count();
   assert.ok(count>0);
   await page.locator('#movers tbody tr').first().waitFor();
   await page.locator('#movers').scrollIntoViewIfNeeded();
   await page.screenshot({path:`tests/movers-${width}.png`});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const mover=page.locator('#movers .ticker').first();
   const ticker=await mover.locator('b').innerText();
   await mover.click();
   assert.equal(new URL(page.url()).searchParams.get('etf'),ticker);
   if(ticker!=='XLE') await page.goBack();
   await page.getByRole('textbox',{name:'Search analytics sectors'}).fill('no-such-sector');
   await page.getByRole('button',{name:'Clear search',exact:true}).click();
   assert.equal(await page.locator('.reference-ranking tbody tr').count(),count);
   await page.locator('.reference-ranking .ticker').filter({hasText:'XLK'}).click();
   await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
   assert.equal(new URL(page.url()).searchParams.get('etf'),'XLK');
   assert.ok(await page.evaluate(()=>scrollY>0));
   await page.goBack();
   await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
   await page.route('**/api/rotation/analytics',route=>route.fulfill({status:503,body:'{}'}));
   await page.getByRole('button',{name:'Reload cached analytics',exact:true}).click();
   await page.getByRole('alert').waitFor();
   assert.match(await page.getByRole('alert').innerText(),/last successfully loaded/);
   assert.equal(await page.locator('.reference-ranking tbody tr').count(),count);
   await page.unroute('**/api/rotation/analytics');
   await page.getByRole('button',{name:'Retry',exact:true}).click();
   await page.getByRole('alert').waitFor({state:'hidden'});
   await page.waitForFunction(()=>!document.querySelector('[aria-label="Reload cached analytics"]').disabled);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   const ranking=page.locator('.reference-ranking .table-scroll');
   assert.ok(await ranking.evaluate(el=>el.scrollHeight>el.clientHeight));
   if(width===390){
    await page.getByRole('combobox',{name:'Chart ETF selection'}).selectOption('XLF');
    await page.getByRole('heading',{name:'XLF holdings',exact:true}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('etf'),'XLF');
   }
   assert.deepEqual(errors,[]);
  } finally {await browser.close();}
 });
}

test('first-load service failure has a recoverable empty state',async()=>{
 const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
 try {
  const page=await browser.newPage();
  await page.route('**/api/rotation/*/holdings',route=>route.fulfill({status:503,body:'{}'}));
  await page.route('**/api/rotation/analytics',route=>route.fulfill({status:503,body:'{}'}));
  await page.goto('http://127.0.0.1:5173/?etf=NOT_A_SYMBOL');
  await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').innerText(),/No analytics loaded/);
  assert.equal(await page.locator('.reference-ranking tbody tr').count(),0);
  assert.equal(await page.getByText('Loading…',{exact:true}).count(),0);
  await page.unroute('**/api/rotation/analytics');
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('etf'),'XLK');
 }finally{await browser.close();}
});

test('slow detail requests time out and offer retry without crashing',async()=>{
 const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:390,height:900}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/rotation/*/line',()=>{});
  await page.route('**/api/rotation/*/holdings',()=>{});
  await page.goto('http://127.0.0.1:5173/');
  await page.getByText('RS history request timed out. Please retry.',{exact:true}).waitFor({timeout:22000});
  await page.getByText('Holdings request timed out. Please retry.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Retry chart',exact:true}).count(),1);
  assert.equal(await page.getByRole('button',{name:'Retry holdings',exact:true}).count(),1);
  await page.unroute('**/api/rotation/*/line');
  await page.getByRole('button',{name:'Retry chart',exact:true}).click();
  await page.locator('.recharts-line-curve').waitFor();
  await page.getByText(/Correction window \(dashed markers\)/).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
