const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/ux1/screenshots');
const requiredStates=['ARMED','TRIGGERED','TRADEABLE','BLOCKED','PORTFOLIO_VETOED','PORTFOLIO_APPROVED'];
const allStates=['NO_SETUP','WATCH','ARMED','TRIGGERED','TRADEABLE','OPTIONS_NOT_SUITABLE','BLOCKED','PORTFOLIO_VETOED','PORTFOLIO_APPROVED'];

test('stored evaluation identity uses one detail GET and never recomputes',async()=>{
 const {createQxV2PreviewFixture}=await import(pathToFileURL(path.resolve(__dirname,'../src/qx-v2-fixtures.js')).href);
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const evaluationId='qxev1_00000000000070008000000000000001';
  let detailGets=0;
  let evaluationPosts=0;
  page.on('request',request=>{
   if(request.url().includes('/api/v2/qx/evaluate/'))evaluationPosts+=1;
  });
  await page.route(`**/api/v2/qx/opportunities/${evaluationId}`,route=>{
   detailGets+=1;
   const decision=createQxV2PreviewFixture('ARMED','SPY');
   route.fulfill({contentType:'application/json',body:JSON.stringify({
    schema_version:'qx.opportunity-detail.v1',evaluation_id:evaluationId,source_mode:'LIVE',
    symbol:'SPY',timeframe:'5m',evaluation_timestamp:decision.evaluation_timestamp,
    request_started_at:decision.request_started_at,recorded_at:decision.evaluation_timestamp,
    expires_at:'2026-09-16T15:00:00Z',freshness_policy_version:'test_v1',
    publication_state:decision.publication_state,lifecycle_state:decision.current_lifecycle_state,
    pipeline_version:'core_v1',config_version:decision.config_version,engine_versions:decision.engine_versions,
    input_fingerprint:'a'.repeat(64),result_sha256:'b'.repeat(64),decision,
   })});
  });
  await page.goto(`${baseUrl}/?page=trade&symbol=SPY&horizon=DAY&timeframe=5m&evaluation_timestamp=2026-09-16T14%3A35%3A00Z&evaluation_id=${evaluationId}`);
  await page.locator('.qx-trade-hero-state').filter({hasText:'ARMED'}).waitFor();
  assert.equal(detailGets,1);
  assert.equal(evaluationPosts,0);
  assert.equal(await page.getByLabel('Canonical evaluation identity').getByText(evaluationId,{exact:true}).count(),1);
 }finally{await browser.close();}
});

async function openFixture(browser,{state='ARMED',width=1440,height=1000,symbol='SPY'}={}){
 const page=await browser.newPage({viewport:{width,height}});
 await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_trade_fixture_enabled:true};});
 const query=new URLSearchParams({page:'trade',symbol,horizon:'DAY',timeframe:'5m',fixture_state:state});
 await page.goto(`${baseUrl}/?${query}`);
 await page.locator('.qx-trade-hero-state').filter({hasText:state}).waitFor();
 return page;
}

test('target navigation is preferred while legacy routes remain compatible',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openFixture(browser);
  const nav=page.getByRole('navigation',{name:'Primary product navigation'});
  assert.deepEqual(await nav.locator('a').allTextContents(),['Today','Opportunities','Trade','Portfolio','Research','System']);
  assert.equal(await nav.getByRole('link',{name:'Trade',exact:true}).getAttribute('aria-current'),'page');
  assert.equal(await page.locator('.qx-left-sidebar').count(),0);
  assert.equal(await page.getByText('INSTITUTIONAL QUICK JUMP:',{exact:true}).count(),0);
  for(const href of await nav.locator('a').evaluateAll(links=>links.map(link=>link.href))){
   const query=new URL(href).searchParams;
   assert.equal(query.get('symbol'),'SPY');
   assert.equal(query.get('horizon'),'DAY');
   assert.equal(query.get('timeframe'),'5m');
  }

  await page.goto(`${baseUrl}/?page=scan&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByText('LEGACY COMPATIBILITY VIEW',{exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'scan');
  assert.equal(await page.getByRole('navigation',{name:'Primary product navigation'}).getByRole('link',{name:'Opportunities',exact:true}).getAttribute('aria-current'),'page');
 }finally{await browser.close();}
});

test('implemented target routes resolve through the consolidated System workspace',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.route('**/api/**',route=>route.fulfill({contentType:'application/json',body:'{}'}));
  await page.goto(`${baseUrl}/?page=today&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByLabel('Today Market Attention Workspace').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'today');
  await page.goto(`${baseUrl}/?page=opportunities&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByLabel('Canonical Opportunities Workspace').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'opportunities');
  await page.goto(`${baseUrl}/?page=portfolio&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByLabel('Canonical Portfolio Workspace').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'portfolio');
  await page.goto(`${baseUrl}/?page=research&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByLabel('Research Workspace').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'research');
  await page.goto(`${baseUrl}/?page=system&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByLabel('System workspace').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'system');
 }finally{await browser.close();}
});

test('live Trade route performs one canonical request with point-in-time context',async()=>{
 const {createQxV2PreviewFixture}=await import(pathToFileURL(path.resolve(__dirname,'../src/qx-v2-fixtures.js')).href);
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const requests=[];
  await page.route('**/api/v2/qx/evaluate/**',route=>{
   requests.push(route.request().url());
   const fixture=createQxV2PreviewFixture('ARMED','SPY');
   fixture.horizon='DAY';fixture.htf_timeframe='1h';fixture.macro_timeframe='1d';
   fixture.direction.factors.push({factor_id:'higher_timeframe',availability:'AVAILABLE',weighted_contribution:10,reliability_multiplier:1,detail:'HTF confirmed structure state: BULLISH'});
   return route.fulfill({contentType:'application/json',body:JSON.stringify(fixture)});
  });
  const evaluationTimestamp='2026-09-16T14:30:00Z';
  const query=new URLSearchParams({page:'trade',symbol:'SPY',horizon:'SWING',timeframe:'15m',evaluation_timestamp:evaluationTimestamp});
  await page.goto(`${baseUrl}/?${query}`);
  await page.locator('.qx-trade-hero-state').filter({hasText:'ARMED'}).waitFor();
  await page.waitForTimeout(250);
  assert.equal(requests.length,1);
  const requestUrl=new URL(requests[0]);
  assert.equal(requestUrl.searchParams.get('timeframe'),'15m');
  assert.equal(requestUrl.searchParams.get('evaluation_timestamp'),evaluationTimestamp);
  assert.equal(await page.getByText('MARKET DRIVER',{exact:true}).count(),1);
  assert.equal(await page.getByLabel('Market Driver').getByText('MARKET DRIVER UNAVAILABLE',{exact:true}).count(),1);
  const multiTimeframe=page.getByLabel('Multi-timeframe context');
  assert.match(await multiTimeframe.innerText(),/5m[\s\S]*1h[\s\S]*Daily/);
  assert.match(await multiTimeframe.innerText(),/SCORE CONTRIBUTION[\s\S]*\+10\.0 pts/i);
  assert.equal(await multiTimeframe.getByText('AVAILABLE',{exact:true}).count(),1);
  assert.equal(await page.getByLabel('Execution Readiness').getByText('NOT ENABLED',{exact:true}).count(),1);
 }finally{await browser.close();}
});

test('all required canonical states remain distinct and WHY stays complete',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const state of allStates){
   const page=await openFixture(browser,{state});
   assert.equal(await page.locator('.qx-trade-hero-state').innerText(),state);
   if(state==='ARMED'){
    assert.match(await page.getByText('What are we waiting for?').locator('..').innerText(),/canonical trigger/i);
    assert.equal(await page.getByText('CONFIRMED',{exact:true}).count(),0);
   }
   if(state==='OPTIONS_NOT_SUITABLE'){
    assert.equal(await page.getByText('NOT_SUITABLE',{exact:true}).count()>0,true);
    assert.equal(await page.getByText('TRADEABLE',{exact:true}).count()>0,true);
   }
   await page.close();
  }

  for(const state of ['ARMED','BLOCKED','PORTFOLIO_VETOED']){
   const page=await openFixture(browser,{state});
   const why=page.locator('.qx-lifecycle-why');
   await why.locator('summary').click();
   assert.notEqual(await why.getAttribute('open'),null);
   for(const label of ['Stage availability','Data freshness & provenance','Reason codes']){
    assert.equal(await page.getByText(label,{exact:true}).count()>0,true,label);
   }
   await page.close();
  }
 }finally{await browser.close();}
});

test('Trade Workspace is responsive, replaces stale symbols, and captures review evidence',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  for(const [label,width,height] of [['desktop',1600,1000],['laptop',1366,900],['mobile',390,844]]){
   const page=await openFixture(browser,{state:'ARMED',width,height});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(artifactDir,`trade-${label}.png`),fullPage:true});
   if(label==='mobile'){
    const orders=await page.locator('.qx-lifecycle-card').evaluateAll(cards=>Object.fromEntries(cards.map(card=>[card.querySelector('h4').textContent,getComputedStyle(card).order])));
    assert.ok(Number(orders['Trigger & Invalidation'])<Number(orders['Structure']));
   }
   await page.close();
  }

  for(const state of requiredStates){
   const page=await openFixture(browser,{state,width:1440,height:1000});
   await page.screenshot({path:path.join(artifactDir,`state-${state.toLowerCase()}.png`),fullPage:true});
   if(['ARMED','BLOCKED','PORTFOLIO_VETOED'].includes(state)){
    await page.locator('.qx-lifecycle-why summary').click();
    await page.screenshot({path:path.join(artifactDir,`state-${state.toLowerCase()}-why-expanded.png`),fullPage:true});
   }
   await page.close();
  }

  const page=await openFixture(browser,{state:'TRIGGERED',symbol:'SPY'});
  const identity=page.getByLabel('Canonical evaluation identity');
  await identity.getByText('SPY',{exact:true}).waitFor();
  await page.getByLabel('Trade symbol').fill('QQQ');
  await page.getByRole('button',{name:'Evaluate',exact:true}).click();
  await identity.getByText('QQQ',{exact:true}).waitFor();
  assert.equal(await identity.getByText('SPY',{exact:true}).count(),0);
  assert.equal(new URL(page.url()).searchParams.get('symbol'),'QQQ');
  await page.close();
 }finally{await browser.close();}
});
