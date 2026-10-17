const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/full_page_activation');

test('live Opportunities discovery scan filters and Trade handoff work end to end',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}});
  const consoleErrors=[];
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  await page.goto(`${baseUrl}/?page=opportunities&horizon=SWING&timeframe=1h`);
  await page.getByRole('heading',{name:'Opportunities',exact:true}).waitFor();
  await page.locator('[data-source="legacy"]').first().waitFor({timeout:30000});
  const liveMovers=page.locator('[data-source="legacy"]');
  assert.equal(await liveMovers.count(),10);
  assert.equal(await liveMovers.getByText('UNAVAILABLE',{exact:true}).count(),0);
  for(const row of await liveMovers.all()){
   assert.match(await row.innerText(),/SECTOR[\s\S]+1D MOVE[\s\S]+SPY EXCESS[\s\S]+DATA AS OF/);
   assert.match(await row.innerText(),/\$\d+\.\d{2}/);
   assert.match(await row.innerText(),/schwab:quote:SPY/);
  }

  const controls=page.getByLabel('Opportunity filters');
  const lifecycle=controls.getByText('Lifecycle').locator('..').locator('select');
  const direction=controls.getByText('Direction').locator('..').locator('select');
  const sort=controls.getByText('Sort').locator('..').locator('select');
  assert.deepEqual(await lifecycle.locator('option').allTextContents(),[
   'ACTIVE','ALL','BLOCKED','NO_SETUP','WATCH','ARMED','TRIGGERED','NOT_TRADEABLE',
   'TRADEABLE','OPTIONS_NOT_SUITABLE','OPTIONS_SUITABLE','PORTFOLIO_VETOED','PORTFOLIO_APPROVED','EXPIRED',
  ]);
  assert.deepEqual(await direction.locator('option').allTextContents(),['ALL','BULLISH','BEARISH','NEUTRAL','UNAVAILABLE']);
  assert.deepEqual(await sort.locator('option').allTextContents(),['Evaluation newest','Symbol','Lifecycle state','Legacy 1D return']);

  const firstSymbol=await page.locator('[data-source="legacy"] .qx-opportunity-symbol strong').first().innerText();
  await page.getByPlaceholder('Symbol, state, thesis').fill(firstSymbol);
  assert.equal(await page.locator('[data-source="legacy"]').count(),1);
  await page.getByPlaceholder('Symbol, state, thesis').fill('');

  await lifecycle.selectOption('ALL');
  await page.waitForTimeout(250);
  await lifecycle.selectOption('ACTIVE');
  await direction.selectOption('BULLISH');
  await direction.selectOption('ALL');
  await sort.selectOption('symbol');
  await sort.selectOption('evaluation_desc');

  const scan=page.getByRole('button',{name:'Evaluate live movers'});
  await scan.click();
  await page.locator('.qx-opportunity-scan small').filter({hasText:/evaluated/}).waitFor({timeout:180000});
  const summary=await page.locator('.qx-opportunity-scan small').innerText();
  assert.match(summary,/\d+ evaluated, \d+ active/);
  assert.ok(await page.locator('[data-source="canonical"]').count()>0);

  await lifecycle.selectOption('ALL');
  const stored=page.locator('[data-source="canonical"]').first();
  const storedSymbol=await stored.locator('.qx-opportunity-symbol strong').innerText();
  await stored.getByRole('link',{name:'Open Trade'}).click();
  await page.getByRole('heading',{name:/Trade Workspace/}).waitFor({timeout:30000});
  assert.equal(new URL(page.url()).searchParams.get('symbol'),storedSymbol);
  assert.equal(new URL(page.url()).searchParams.get('timeframe'),'1h');

  await page.goBack();
  await page.getByRole('heading',{name:'Opportunities',exact:true}).waitFor();
  for(const [name,timeframe] of [['DAY','5m'],['INVEST','1d'],['SWING','1h']]){
   await page.getByRole('group',{name:'Opportunity horizon'}).getByRole('button',{name}).click();
   await page.waitForFunction(expected=>new URL(location.href).searchParams.get('timeframe')===expected,timeframe);
  }
  await page.locator('[data-source="legacy"]').first().waitFor({timeout:30000});
  await page.getByLabel('Opportunity filters').getByText('Lifecycle').locator('..').locator('select').selectOption('ALL');
  await page.locator('[data-source="canonical"]').first().waitFor({timeout:30000});
  await page.screenshot({path:path.join(artifactDir,'opportunities-live-functional.png'),fullPage:true});
  assert.deepEqual(consoleErrors,[]);
 }finally{await browser.close();}
});
