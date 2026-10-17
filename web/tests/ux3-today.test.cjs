const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/ux3/screenshots');
const moversPayload={rows:[{etf:'AMD',name:'Advanced Micro Devices',sector:'Information Technology',as_of:'2026-09-16T14:35:00Z',return_1d:0.024,excess_1d:0.013,source:'schwab'}]};

async function mockReadOnlySources(page,{canonicalPayload}={}){
 const {createQxV2PreviewFixture}=await import(pathToFileURL(path.resolve(__dirname,'../src/qx-v2-fixtures.js')).href);
 await page.route('**/api/v2/qx/evaluate/**',route=>{
  const symbol=new URL(route.request().url()).pathname.split('/').pop();
  route.fulfill({contentType:'application/json',body:JSON.stringify(createQxV2PreviewFixture('WATCH',symbol))});
 });
 await page.route('**/api/ops/health',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({status:'OK',components:[]})}));
 await page.route('**/api/schwab/movers',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(moversPayload)}));
 await page.route('**/api/v2/qx/opportunities?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(canonicalPayload||{schema_version:'qx.opportunity-list.v1',pipeline_version:'core_v1',source_mode:'LIVE',items:[],next_cursor:null,has_more:false})}));
}

async function openToday(browser,{state='armed',fixtures=true,width=1440,height=900,horizon='DAY',canonicalPayload,opportunityRequests}={}){
 const page=await browser.newPage({viewport:{width,height}});
 if(opportunityRequests)page.on('request',request=>{if(request.url().includes('/api/v2/qx/opportunities'))opportunityRequests.push(request.url());});
 if(fixtures) await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_today_fixture_enabled:true,qx_opportunities_fixture_enabled:true,qx_trade_fixture_enabled:true};});
 await mockReadOnlySources(page,{canonicalPayload});
 const query=new URLSearchParams({page:'today',horizon,timeframe:horizon==='DAY'?'5m':horizon==='SWING'?'1h':'1d'});
 if(fixtures) query.set('today_state',state);
 await page.goto(`${baseUrl}/?${query}`);
 await page.getByRole('heading',{name:'What Matters Now?'}).waitFor();
 return page;
}

test('Today preserves the approved attention hierarchy and truthful source labels',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openToday(browser,{state:'armed'});
  const headings=await page.locator('.qx-today-section-heading h2').allTextContents();
  assert.deepEqual(headings,['Market Pulse','Market Drivers','Active QX Opportunities','Positions Requiring Attention','Material Events / Data Health']);
  assert.equal(await page.getByLabel('Today Market Attention Workspace').getByText('TEST / PREVIEW DATA - NOT LIVE',{exact:true}).count(),1);
  const drivers=page.getByRole('heading',{name:'Market Drivers'}).locator('xpath=ancestor::section[1]');
  assert.equal(await drivers.getByText('UNAVAILABLE',{exact:true}).count(),1);
  assert.equal(await page.getByLabel('Legacy market movement context').getByText('LEGACY SOURCE',{exact:true}).count(),1);
  assert.equal(await page.locator('.qx-today-opportunity .qx-state').allTextContents().then(states=>states.includes('ARMED')),true);
  const positions=page.getByRole('heading',{name:'Positions Requiring Attention'}).locator('xpath=ancestor::section[1]');
  assert.equal(await positions.getByText('UNAVAILABLE',{exact:true}).count()>0,true);
 }finally{await browser.close();}
});

test('unavailable Market Driver stays truthful and compact on desktop and mobile',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const [label,width,height] of [['desktop',1440,900],['mobile',390,844]]){
   const page=await openToday(browser,{state:'armed',width,height});
   const drivers=page.locator('.qx-today-drivers');
   const unavailable=drivers.locator('.qx-today-unavailable');
   assert.equal(await unavailable.getByText('UNAVAILABLE',{exact:true}).count(),1,label);
   assert.match(await unavailable.innerText(),/No driver is inferred/);
   const box=await unavailable.boundingBox();
   assert.ok(box.height<65,`${label} unavailable state height ${box.height}px`);
   await page.close();
  }
 }finally{await browser.close();}
});

test('canonical Today opportunity routes to Trade with the same evaluation context',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openToday(browser,{state:'triggered',horizon:'SWING'});
  const triggered=page.locator('.qx-today-opportunity').filter({hasText:'TRIGGERED'}).first();
  await triggered.getByRole('link',{name:'Open Trade'}).click();
  await page.getByRole('heading',{name:/Trade Workspace/}).waitFor();
  await page.locator('.qx-trade-hero-state').filter({hasText:'TRIGGERED'}).waitFor();
  const url=new URL(page.url());
  assert.equal(url.searchParams.get('page'),'trade');
  assert.equal(url.searchParams.get('symbol'),'QQQ');
  assert.equal(url.searchParams.get('horizon'),'SWING');
  assert.equal(url.searchParams.get('timeframe'),'1h');
  assert.equal(url.searchParams.get('evaluation_timestamp'),'2026-09-16T14:35:00Z');
  assert.equal(url.searchParams.get('evaluation_id'),'fixture-swing-triggered-qqq');
  assert.equal(url.searchParams.has('etf'),false);
  assert.equal(await page.getByLabel('Canonical evaluation identity').getByText('1h',{exact:true}).count(),1);
 }finally{await browser.close();}
});

test('live Today consumes actual list shape and requests attention states server-side',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
 const canonicalPayload={
   schema_version:'qx.opportunity-list.v1',pipeline_version:'core_v1',source_mode:'LIVE',next_cursor:null,has_more:false,
   items:[{
    evaluation_id:'qxev1_00000000000070008000000000000001',symbol:'SPY',timeframe:'5m',evaluation_timestamp:'2026-09-16T14:30:00Z',
    source_mode:'LIVE',
    pipeline_version:'core_v1',publication_state:'VERIFIED',lifecycle_state:'ARMED',direction:'BULLISH',primary_playbook_id:'ORB',
    trigger:500,invalidation:495,evidence_coverage:.8,reason_codes:[],data_dependencies:{},
   }],
  };
  const opportunityRequests=[];
  const page=await openToday(browser,{fixtures:false,canonicalPayload,opportunityRequests});
  await page.locator('.qx-today-opportunity').filter({hasText:'SPY'}).waitFor();
  assert.equal(opportunityRequests.length,1);
  const url=new URL(opportunityRequests[0]);
  assert.deepEqual(url.searchParams.getAll('states'),['WATCH','ARMED','TRIGGERED','TRADEABLE','OPTIONS_SUITABLE']);
  assert.equal(url.searchParams.get('include_terminal'),'false');
  assert.equal(url.searchParams.get('fresh_only'),'true');
 }finally{await browser.close();}
});

test('SPX index quote explains broker fields that are not published',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await mockReadOnlySources(page);
  await page.route('**/api/v2/market/quote/*',route=>{
   const symbol=new URL(route.request().url()).pathname.split('/').pop();
   const index=symbol==='SPX';
   route.fulfill({contentType:'application/json',body:JSON.stringify({
    symbol,resolved_symbol:index?'$SPX':symbol,asset_type:index?'INDEX':'EQUITY',source:'schwab',status:'AVAILABLE',
    last:index?7637.76:700,bid:index?null:699.99,ask:index?null:700.01,change_pct:0,volume:1234,
    quote_timestamp:'2026-09-17T20:34:50Z',trade_timestamp:'2026-09-17T20:34:50Z',realtime:true,
    retrieved_at:'2026-09-18T12:35:00Z',age_seconds:57610,freshness:'STALE',
    field_evidence:{
     last:{availability:'AVAILABLE',source:'schwab',reason_code:null},
     bid:{availability:index?'NOT_PUBLISHED':'AVAILABLE',source:'schwab',reason_code:index?'INDEX_NO_EXECUTABLE_ORDER_BOOK':null},
     ask:{availability:index?'NOT_PUBLISHED':'AVAILABLE',source:'schwab',reason_code:index?'INDEX_NO_EXECUTABLE_ORDER_BOOK':null},
     change_pct:{availability:'AVAILABLE',source:'schwab',reason_code:null},
     volume:{availability:'AVAILABLE',source:'schwab',reason_code:null},
    },
   })});
  });
  await page.goto(`${baseUrl}/?page=today&horizon=SWING&timeframe=1h`);
  const card=page.locator('.qx-pulse-card').filter({hasText:'SPX'}).first();
  await card.getByText('AVAILABLE',{exact:true}).waitFor();
  assert.equal(await card.getByText('NOT PUBLISHED',{exact:true}).count(),2);
  assert.match(await card.locator('.qx-pulse-field-note').innerText(),/INDEX snapshot without an executable order book/);
  await card.locator('summary').click();
  assert.equal(await card.getByText(/INDEX_NO_EXECUTABLE_ORDER_BOOK/).count(),2);
 }finally{await browser.close();}
});

test('Today empty, unavailable, blocked, and partial states remain distinct',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const noOpportunity=await openToday(browser,{state:'no_opportunities'});
  assert.equal(await noOpportunity.getByText('NO CURRENT QUALIFYING OPPORTUNITIES',{exact:true}).count(),1);
  await noOpportunity.close();

  const live=await openToday(browser,{fixtures:false});
  assert.equal(await live.getByText('NO CURRENT QUALIFYING OPPORTUNITIES',{exact:true}).count(),1);
  assert.equal(await live.getByText('No current canonical LIVE observations require attention.',{exact:true}).count(),1);
  assert.equal(await live.locator('.qx-today-opportunity').count(),0);
  await live.close();

  const blocked=await openToday(browser,{state:'market_blocked'});
  assert.equal(await blocked.locator('.qx-pulse-card').filter({hasText:'SPY'}).getByText('BLOCKED',{exact:true}).count(),1);
  assert.equal(await blocked.getByText('SPY canonical pipeline blocked',{exact:true}).count(),1);
  const systemHref=await blocked.locator('.qx-health-alerts > a').filter({hasText:'SPY canonical pipeline blocked'}).getAttribute('href');
  assert.equal(new URL(systemHref,baseUrl).searchParams.get('page'),'system');
  await blocked.close();

  const partial=await openToday(browser,{state:'partial_positions'});
  const positions=partial.getByRole('heading',{name:'Positions Requiring Attention'}).locator('xpath=ancestor::section[1]');
  assert.equal(await positions.getByText('PARTIAL',{exact:true}).count(),1);
  assert.match(await positions.innerText(),/account evidence is partial/i);
  await partial.close();
 }finally{await browser.close();}
});

test('Today routes to Opportunities and preserves horizon context',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openToday(browser,{state:'armed',horizon:'INVEST'});
  const href=await page.getByRole('link',{name:/View all opportunities/i}).getAttribute('href');
  const url=new URL(href,baseUrl);
  assert.equal(url.searchParams.get('page'),'opportunities');
  assert.equal(url.searchParams.get('horizon'),'INVEST');
  assert.equal(url.searchParams.get('timeframe'),'1d');
 }finally{await browser.close();}
});

test('Today does not inject or propagate stale symbol context',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openToday(browser,{state:'armed'});
  await page.goto(`${baseUrl}/?page=today&symbol=XLK&etf=XLK&today_state=armed`);
  await page.getByRole('heading',{name:'What Matters Now?'}).waitFor();
  assert.equal(await page.getByText('Ticker: XLK').count(),0);
  const href=await page.getByRole('link',{name:/View all opportunities/i}).getAttribute('href');
  const destination=new URL(href,baseUrl);
  assert.equal(destination.searchParams.has('symbol'),false);
  assert.equal(destination.searchParams.has('etf'),false);
 }finally{await browser.close();}
});

test('live Today performs bounded read-only requests without canonical opportunity evaluation duplication',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const requests=[];
  page.on('request',request=>{if(request.url().includes('/api/'))requests.push(`${request.method()} ${new URL(request.url()).pathname}`);});
  await mockReadOnlySources(page);
  await page.goto(`${baseUrl}/?page=today&horizon=DAY&timeframe=5m`);
  await page.getByRole('heading',{name:'What Matters Now?'}).waitFor();
  await page.locator('.qx-pulse-card').filter({hasText:'SPY'}).getByText('AVAILABLE',{exact:true}).waitFor();
  await page.waitForTimeout(250);
  assert.equal(requests.filter(value=>value.includes('/api/v2/qx/evaluate/SPY')).length,1);
  assert.equal(requests.filter(value=>value.includes('/api/v2/qx/evaluate/QQQ')).length,1);
  assert.equal(requests.filter(value=>value.includes('/api/ops/health')).length,1);
  assert.equal(requests.filter(value=>value.includes('/api/schwab/movers')).length,1);
  assert.equal(requests.filter(value=>value.includes('/api/v2/qx/opportunities')).length,1);
 }finally{await browser.close();}
});

test('Today is responsive and captures required review states',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  for(const [label,width,height] of [['desktop',1600,1000],['laptop',1366,900],['tablet',768,1024],['mobile',390,844]]){
   const page=await openToday(browser,{state:'triggered',width,height});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label);
   await page.screenshot({path:path.join(artifactDir,`today-${label}.png`),fullPage:true});
   if(label==='mobile'){
    const sectionTitles=await page.locator('.qx-today-section-heading h2').allTextContents();
    assert.deepEqual(sectionTitles,['Market Pulse','Market Drivers','Active QX Opportunities','Positions Requiring Attention','Material Events / Data Health']);
   }
   await page.close();
  }
  for(const [state,name] of [['armed','today-armed.png'],['triggered','today-triggered.png'],['no_opportunities','today-no-opportunity.png'],['market_blocked','today-blocked-data-quality.png'],['partial_positions','today-partial-position-data.png']]){
   const page=await openToday(browser,{state,width:1440,height:900});
   await page.screenshot({path:path.join(artifactDir,name),fullPage:true});
   await page.close();
  }
 }finally{await browser.close();}
});

test('legacy Today routes remain compatibility surfaces',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:900}});
  await page.route('**/api/**',route=>route.fulfill({contentType:'application/json',body:'{}'}));
  for(const route of ['command_center','morning_report','daily_workflow']){
   await page.goto(`${baseUrl}/?page=${route}&symbol=SPY&horizon=DAY&timeframe=5m`);
   await page.getByText('LEGACY COMPATIBILITY VIEW',{exact:true}).waitFor();
   assert.equal(new URL(page.url()).searchParams.get('page'),route);
   assert.equal(await page.getByRole('navigation',{name:'Primary product navigation'}).getByRole('link',{name:'Today',exact:true}).getAttribute('aria-current'),'page');
  }
 }finally{await browser.close();}
});
