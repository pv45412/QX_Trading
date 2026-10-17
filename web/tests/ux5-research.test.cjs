const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/ux5/screenshots');

async function fixtureModule(){return import(pathToFileURL(path.resolve(__dirname,'../src/qx-research-fixtures.js')).href);}

async function mockResearch(page,{optionsIdeas=null,analytics=null,snapshotUnavailable=false,lineUnavailable=false,holdingsUnavailable=false,analyticsUnavailable=false}={}){
 const f=await fixtureModule();
 await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_research_fixture_enabled:true};});
 await page.route('**/api/market/*/snapshot',route=>{const parts=new URL(route.request().url()).pathname.split('/');route.fulfill({json:snapshotUnavailable?{symbol:decodeURIComponent(parts[3]),status:'UNAVAILABLE',source_class:'UNAVAILABLE',last_price:null,structure:null,reason_code:'SOURCE_BARS_UNAVAILABLE'}:f.researchSnapshotFixture(decodeURIComponent(parts[3]))});});
 await page.route('**/api/rotation/analytics',route=>analyticsUnavailable?route.fulfill({status:503,json:{detail:'Unavailable'}}):route.fulfill({json:analytics ?? f.researchAnalyticsFixture()}));
 await page.route('**/api/rotation/*/line',route=>{if(lineUnavailable)return route.fulfill({status:503,json:{detail:'Unavailable'}});const parts=new URL(route.request().url()).pathname.split('/');return route.fulfill({json:f.researchLineFixture(parts[3])});});
 await page.route('**/api/rotation/*/holdings',route=>{if(holdingsUnavailable)return route.fulfill({status:503,json:{detail:'Unavailable'}});const parts=new URL(route.request().url()).pathname.split('/');return route.fulfill({json:f.researchHoldingsFixture(parts[3])});});
 await page.route('**/api/options-scanner/ideas',route=>route.fulfill({json:optionsIdeas ?? f.researchOptionsFixture()}));
 await page.route('**/api/strategies/workspace/*',route=>route.fulfill({json:f.researchStrategyFixture()}));
 await page.route('**/api/strategies/payoff',route=>route.fulfill({json:f.researchPayoffFixture()}));
 await page.route('**/api/backtest/run',route=>route.fulfill({json:f.researchBacktestFixture(JSON.parse(route.request().postData()||'{}').symbol)}));
}

async function openResearch(browser,{mode='symbol',width=1440,height=900,pageName='research'}={}){
 const page=await browser.newPage({viewport:{width,height}});await mockResearch(page);
 const modePart=pageName==='research'?`&research_mode=${mode}`:'';
 await page.goto(`${baseUrl}/?page=${pageName}&symbol=NVDA&horizon=SWING&timeframe=1d&research_fixture=1${modePart}`);
 await page.getByRole('heading',{name:'Research',exact:true}).waitFor();return page;
}

test('Symbol Research stays source-backed and hands off to fresh Trade context',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openResearch(browser);
  await page.getByText('SOURCE-BACKED',{exact:true}).waitFor();
  assert.equal(await page.getByText('SOURCE-BACKED',{exact:true}).count()>0,true);
  assert.equal(await page.getByText('BEARISH_BOS',{exact:true}).count(),1);
  assert.equal(await page.locator('.qx-research-stage .qx-state').count(),0);
  await page.getByRole('link',{name:/Open in Trade/}).click();const url=new URL(page.url());
  assert.equal(url.searchParams.get('page'),'trade');assert.equal(url.searchParams.get('symbol'),'NVDA');
  assert.equal(url.searchParams.get('horizon'),'SWING');assert.equal(url.searchParams.get('timeframe'),'1d');
  assert.equal(url.searchParams.has('evaluation_timestamp'),false);assert.equal(url.searchParams.has('evaluation_id'),false);
 }finally{await browser.close();}
});

test('ETF mode owns constituents and remains distinct from broker Portfolio',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openResearch(browser,{mode:'etf_sector'});
  assert.equal(await page.getByRole('heading',{name:/XLK ETF Constituents/}).count(),1);
  assert.equal(await page.getByText('ETF CONSTITUENTS / NOT PORTFOLIO',{exact:true}).count(),1);
  assert.equal(await page.getByRole('button',{name:'Fund weights'}).count(),1);
  assert.equal(await page.getByText('Canonical broker positions; never ETF constituents').count(),0);
 }finally{await browser.close();}
});

test('Relative Strength mode consolidates ranking and movers without duplicate analytics calls',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1440,height:900}});await mockResearch(page);let calls=0;
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/rotation/analytics')calls+=1;});
  await page.goto(`${baseUrl}/?page=research&research_mode=relative_strength&research_fixture=1`);
  await page.getByRole('heading',{name:'Relative Strength / Rotation'}).waitFor();
  assert.equal(await page.getByText('Sector Relative Strength & Rotation Studio').count(),1);assert.equal(calls,1);
 }finally{await browser.close();}
});

test('inactive Research modes do not issue unrelated data requests',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1440,height:900}});await mockResearch(page);const paths=[];
  page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/'))paths.push(new URL(request.url()).pathname);});
  await page.goto(`${baseUrl}/?page=research&research_mode=symbol&symbol=NVDA&research_fixture=1`);await page.getByText('BEARISH_BOS',{exact:true}).waitFor();
  assert.deepEqual(paths.filter(value=>value.includes('/api/market/')),['/api/market/NVDA/snapshot']);
  assert.equal(paths.some(value=>value.includes('/rotation/analytics')||value.includes('/holdings')||value.includes('/options-scanner')||value.includes('/backtest')),false);
 }finally{await browser.close();}
});

test('Options research is modeled and legacy-labeled, never canonical Phase 9',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openResearch(browser,{mode:'options_strategy'});
  assert.equal(await page.getByText('MODELED',{exact:true}).count()>=2,true);assert.equal(await page.getByText('LEGACY',{exact:true}).count()>=1,true);
  assert.equal(await page.getByText('NOT CANONICAL PHASE 9',{exact:true}).count(),1);
  assert.equal(await page.getByText('PORTFOLIO_APPROVED',{exact:true}).count(),0);
 }finally{await browser.close();}
});

test('Options research never fabricates summary values when ideas are unavailable',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1440,height:900}});await mockResearch(page,{optionsIdeas:{ideas:[]}});
  await page.goto(`${baseUrl}/?page=research&research_mode=options_strategy&research_fixture=1`);await page.getByRole('heading',{name:'Options / Strategy Research'}).waitFor();
  assert.equal(await page.getByText('NVDA 2027-09-17 Call',{exact:true}).count(),0);assert.equal(await page.getByText('AAPL (IV 21% vs RV 18%)',{exact:true}).count(),0);
  assert.equal(await page.getByText('TSLA Put Spread',{exact:true}).count(),0);assert.equal(await page.getByText('78%',{exact:true}).count(),0);
 }finally{await browser.close();}
});

test('Rotation excludes rows without source-backed quadrant inputs',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1440,height:900}});await mockResearch(page,{analytics:{coverage:1,universe:1,rows:[{etf:'XLK',sector:'Technology',status:'CACHED_UNVERIFIED',source:'fixture_cache',as_of:'2026-09-16T20:00:00Z',rs_change:null,days_off_high:null}]}});
  await page.goto(`${baseUrl}/?page=research&research_mode=relative_strength&research_fixture=1`);await page.getByRole('heading',{name:'Relative Strength / Rotation'}).waitFor();
  assert.equal(await page.locator('.qx-quadrant .qx-chip').count(),0);
 }finally{await browser.close();}
});

test('Research panels change source labels when child APIs are unavailable',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1440,height:900}});await mockResearch(page,{snapshotUnavailable:true,lineUnavailable:true,holdingsUnavailable:true,analyticsUnavailable:true});
  await page.goto(`${baseUrl}/?page=research&research_mode=etf_sector&research_fixture=1`);await page.getByText('Date-aligned cached RS history unavailable.').waitFor();await page.getByText('Compatible saved fund holdings are unavailable.').waitFor();
  assert.equal(await page.locator('.qx-research-stage').getByText('UNAVAILABLE',{exact:true}).count(),2);
  await page.goto(`${baseUrl}/?page=research&research_mode=relative_strength&research_fixture=1`);await page.getByText('The local analytics service is unavailable.',{exact:false}).first().waitFor();
  assert.equal(await page.locator('.qx-research-stage').getByText('UNAVAILABLE',{exact:true}).count(),2);
  await page.goto(`${baseUrl}/?page=research&research_mode=historical&symbol=NVDA&research_fixture=1`);await page.getByText('RESEARCH DATA UNAVAILABLE',{exact:true}).waitFor();
  assert.equal(await page.locator('.qx-research-stage').getByText('UNAVAILABLE',{exact:true}).count(),1);
 }finally{await browser.close();}
});

test('Historical mode keeps simulated results separate from live confidence',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openResearch(browser,{mode:'historical'});
  await page.getByRole('button',{name:/Run NVDA backtest/}).click();await page.getByText('Historical trades',{exact:true}).waitFor();
  assert.equal(await page.getByText('HISTORICAL',{exact:true}).count()>=2,true);assert.equal(await page.getByText('SIMULATED',{exact:true}).count(),1);
  assert.equal(await page.getByText(/not current trade confidence/i).count(),1);
 }finally{await browser.close();}
});

test('Long-Term Thesis is user-entered, non-persisted, and non-recommendational',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openResearch(browser,{mode:'long_term'});
  await page.getByLabel('Research thesis').fill('Review durable evidence quarterly.');
  assert.equal(await page.getByText('USER-ENTERED',{exact:true}).count(),1);assert.equal(await page.getByText('LOCAL SESSION / NOT PERSISTED',{exact:true}).count(),1);
  await page.reload();await page.getByLabel('Research thesis').waitFor();assert.equal(await page.getByLabel('Research thesis').inputValue(),'');
 }finally{await browser.close();}
});

test('Legacy research routes remain compatibility aliases to the consolidated modes',async()=>{
 const browser=await chromium.launch({headless:true});try{for(const [route,heading] of [['ticker_history','Symbol Research'],['relative_strength','Relative Strength / Rotation'],['options_ideas','Options / Strategy Research'],['backtest','Historical / Backtest']]){
  const page=await openResearch(browser,{pageName:route});assert.equal(await page.getByText('LEGACY COMPATIBILITY VIEW',{exact:true}).count(),1,route);assert.equal(await page.getByRole('heading',{name:heading,exact:true}).count(),1,route);await page.close();
 }}finally{await browser.close();}
});

test('Research modes remain responsive and produce approved review captures',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});const browser=await chromium.launch({headless:true});try{
  for(const [label,width,height] of [['desktop',1920,945],['laptop',1440,900],['mobile',390,844]]){const page=await openResearch(browser,{width,height});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label);
   if(label==='mobile')assert.equal(await page.locator('.qx-research-modes').evaluate(node=>node.scrollWidth===node.clientWidth),true,'mobile mode navigation must not clip');
   await page.screenshot({path:path.join(artifactDir,`research-${label}.png`),fullPage:true});await page.close();}
  for(const mode of ['symbol','etf_sector','relative_strength','options_strategy','historical','long_term']){const page=await openResearch(browser,{mode,width:1440,height:900});
   if(mode==='options_strategy')await page.getByText(/Option Leg At-Expiration Payoff Curve/).waitFor();
   if(mode==='historical'){await page.getByRole('button',{name:/Run NVDA backtest/}).click();await page.getByText('Historical trades',{exact:true}).waitFor();}
   await page.screenshot({path:path.join(artifactDir,`research-${mode}.png`),fullPage:true});await page.close();}
 }finally{await browser.close();}
});
