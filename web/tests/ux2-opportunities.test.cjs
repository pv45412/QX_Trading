const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/ux2/screenshots');
const moversPayload={rows:[
 {etf:'AMD',name:'Advanced Micro Devices',sector:'Information Technology',industry:'Semiconductors',as_of:'2026-09-15T20:00:00Z',return_1d:0.024,excess_1d:0.013,last:180,benchmark_source:'schwab:quote:SPY',source:'schwab'},
 {etf:'JPM',name:'JPMorgan Chase',sector:'Financials',industry:'Diversified Banks',as_of:'2026-09-15T20:00:00Z',return_1d:-0.004,excess_1d:-0.011,last:300,benchmark_source:'schwab:quote:SPY',source:'schwab'},
]};

async function openOpportunities(browser,{fixtures=true,width=1440,height=900,horizon='DAY'}={}){
 const page=await browser.newPage({viewport:{width,height}});
 if(fixtures) await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_opportunities_fixture_enabled:true,qx_trade_fixture_enabled:true};});
 await page.route('**/api/v2/qx/opportunities?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({schema_version:'qx.opportunity-list.v1',pipeline_version:'core_v1',source_mode:'LIVE',items:[],next_cursor:null,has_more:false})}));
 await page.route('**/api/schwab/movers',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(moversPayload)}));
 const query=new URLSearchParams({page:'opportunities',horizon,timeframe:horizon==='DAY'?'5m':horizon==='SWING'?'1h':'1d'});
 await page.goto(`${baseUrl}/?${query}`);
 await page.getByRole('heading',{name:'Opportunities',exact:true}).waitFor();
 return page;
}

test('live Opportunities shows a truthful empty canonical result without manufacturing candidates',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser,{fixtures:false});
  await page.getByText('NO CURRENT QUALIFYING OPPORTUNITIES',{exact:true}).waitFor();
  assert.equal(await page.getByText('NO CURRENT QUALIFYING OPPORTUNITIES',{exact:true}).count(),1);
  assert.match(await page.getByText(/No current ACTIVE evaluations match/).innerText(),/ACTIVE evaluations/i);
  assert.equal(await page.getByRole('button',{name:'Show all evaluations'}).count(),1);
  assert.equal(await page.locator('[data-source="canonical"]').count(),0);
  assert.equal(await page.locator('[data-source="legacy"]').count(),2);
  assert.equal(await page.locator('[data-source="legacy"] .qx-legacy-source-badge').count(),2);
  assert.equal(await page.locator('[data-source="legacy"] .qx-state').count(),0);
  assert.equal(await page.getByText('TEST / PREVIEW DATA - NOT LIVE',{exact:true}).count(),0);
  const amd=page.locator('[data-source="legacy"]').filter({hasText:'AMD'});
  for(const value of ['Advanced Micro Devices','Information Technology','Semiconductors','$180.00','+1.30%','schwab:quote:SPY']){
   assert.equal(await amd.getByText(value,{exact:true}).count(),1,value);
  }
  await page.locator('.qx-opportunities-controls select').first().selectOption('BLOCKED');
  await page.getByText(/No current canonical evaluations match BLOCKED filters/).waitFor();
  assert.equal(await page.getByRole('button',{name:'Clear filters'}).count(),1);
 }finally{await browser.close();}
});

test('live mover scan evaluates bounded symbols and reveals terminal outcomes',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const evaluated=[];
  await page.route('**/api/schwab/movers',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(moversPayload)}));
  await page.route('**/api/v2/qx/evaluate/**',route=>{
   const symbol=decodeURIComponent(new URL(route.request().url()).pathname.split('/').at(-1));
   evaluated.push(symbol);
   route.fulfill({contentType:'application/json',body:JSON.stringify({symbol,timeframe:'5m',current_lifecycle_state:'NO_SETUP'})});
  });
  await page.route('**/api/v2/qx/opportunities?**',route=>{
   const url=new URL(route.request().url());
   const includeTerminal=url.searchParams.get('include_terminal')==='true';
   const items=includeTerminal?evaluated.map((symbol,index)=>({
    evaluation_id:`qxev1_${String(index+1).padStart(32,'0')}`,source_mode:'LIVE',symbol,timeframe:'5m',
    horizon_context:'DAY',evaluation_timestamp:'2026-09-17T18:30:00Z',recorded_at:'2026-09-17T18:30:01Z',
    expires_at:'2026-09-17T18:45:00Z',publication_state:'RESEARCH_ONLY',lifecycle_state:'NO_SETUP',
    pipeline_version:'core_v1',config_version:'research_v1',reason_codes:['NO_SETUP'],data_dependencies:{},visibility_state:'CURRENT',
   })):[];
   route.fulfill({contentType:'application/json',body:JSON.stringify({source_mode:'LIVE',pipeline_version:'core_v1',items,next_cursor:null,has_more:false})});
  });
  await page.goto(`${baseUrl}/?page=opportunities&horizon=DAY&timeframe=5m`);
  const scan=page.getByRole('button',{name:'Evaluate live movers'});
  await scan.waitFor();
  await scan.click();
  await page.getByText('2 evaluated, 0 active.').waitFor();
  assert.deepEqual(evaluated,['AMD','JPM']);
  assert.equal(await page.locator('[data-source="canonical"]').count(),2);
  assert.equal(await page.getByLabel('Opportunity filters').getByText('Lifecycle').locator('..').locator('select').inputValue(),'ALL');
 }finally{await browser.close();}
});

test('invalid canonical store remains unavailable while legacy discovery stays labeled',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.route('**/api/v2/qx/opportunities?**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{code:'OPPORTUNITY_STORE_SCHEMA_INVALID'}})}));
  await page.route('**/api/schwab/movers',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(moversPayload)}));
  await page.goto(`${baseUrl}/?page=opportunities&horizon=DAY&timeframe=5m`);
  await page.getByRole('alert').filter({hasText:'Canonical opportunities unavailable (503).'}).waitFor();
  assert.equal(await page.locator('[data-source="canonical"]').count(),0);
  assert.equal(await page.locator('[data-source="legacy"]').count(),2);
  assert.equal(await page.locator('[data-source="legacy"] .qx-legacy-source-badge').count(),2);
 }finally{await browser.close();}
});

test('live Opportunities consumes API-shaped rows, server filters, and cursor pages',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const requests=[];
  await page.route('**/api/v2/qx/opportunities?**',route=>{
   const url=new URL(route.request().url());
   requests.push(url);
   const secondPage=url.searchParams.get('cursor')==='cursor-1';
    const item={
     evaluation_id:secondPage?'qxev1_00000000000070008000000000000002':'qxev1_00000000000070008000000000000001',
     source_mode:'LIVE',
    symbol:secondPage?'QQQ':'SPY',timeframe:'5m',evaluation_timestamp:secondPage?'2026-09-16T14:29:00Z':'2026-09-16T14:30:00Z',
    pipeline_version:'core_v1',publication_state:'VERIFIED',lifecycle_state:secondPage?'TRIGGERED':'ARMED',direction:'BULLISH',
    primary_playbook_id:'ORB',trigger:500,invalidation:495,evidence_coverage:.8,reason_codes:[],data_dependencies:{},
   };
   route.fulfill({contentType:'application/json',body:JSON.stringify({
    schema_version:'qx.opportunity-list.v1',pipeline_version:'core_v1',source_mode:'LIVE',items:[item],
    next_cursor:secondPage?null:'cursor-1',has_more:!secondPage,
   })});
  });
  await page.route('**/api/schwab/movers',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(moversPayload)}));
  await page.goto(`${baseUrl}/?page=opportunities&horizon=DAY&timeframe=5m`);
  await page.locator('[data-source="canonical"]').filter({hasText:'SPY'}).waitFor();
  assert.equal(requests[0].searchParams.get('timeframe'),'5m');
  assert.equal(requests[0].searchParams.get('fresh_only'),'true');
  await page.getByRole('button',{name:'Load more'}).click();
  await page.locator('[data-source="canonical"]').filter({hasText:'QQQ'}).waitFor();
  assert.equal(requests.some(url=>url.searchParams.get('cursor')==='cursor-1'),true);

  const finalRequest=page.waitForRequest(request=>{
   const url=new URL(request.url());
   return url.pathname==='/api/v2/qx/opportunities'&&url.searchParams.get('states')==='ARMED'&&url.searchParams.get('direction')==='BULLISH';
  });
  await page.getByLabel('Opportunity filters').getByText('Lifecycle').locator('..').locator('select').selectOption('ARMED');
  await page.getByLabel('Opportunity filters').getByText('Direction').locator('..').locator('select').selectOption('BULLISH');
  const filteredUrl=new URL((await finalRequest).url());
  assert.equal(filteredUrl.searchParams.get('include_terminal'),'false');
  assert.equal(filteredUrl.searchParams.get('include_blocked'),'false');
 }finally{await browser.close();}
});

test('canonical fixture rows expose required decision fields and direct filters',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser);
  assert.equal(await page.locator('[data-source="canonical"]').count(),5);
  const armed=page.locator('[data-source="canonical"]').filter({hasText:'ARMED'}).first();
  for(const label of ['State','Direction','Playbook / thesis','Market Driver','Trigger / risk','Tradeability','Portfolio','Coverage','Freshness']){
   assert.equal(await armed.getByText(label,{exact:true}).count(),1,label);
  }
  assert.equal(await armed.getByText('UNAVAILABLE',{exact:true}).count()>0,true);
  await page.getByLabel('Opportunity filters').getByText('Lifecycle').locator('..').locator('select').selectOption('ALL');
  assert.equal(await page.locator('[data-source="canonical"]').count(),9);
  await page.getByLabel('Opportunity filters').getByText('Lifecycle').locator('..').locator('select').selectOption('ARMED');
  assert.equal(await page.locator('[data-source="canonical"]').count(),1);
  assert.equal(await page.locator('[data-source="canonical"] .qx-state').innerText(),'ARMED');
  await page.getByPlaceholder('Symbol, state, thesis').fill('ZZZZ');
  assert.equal(await page.getByText('NO CURRENT QUALIFYING OPPORTUNITIES',{exact:true}).count(),1);
 }finally{await browser.close();}
});

test('horizon changes context and timeframe without changing lifecycle semantics',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser);
  const statesBefore=await page.locator('[data-source="canonical"] .qx-state').allTextContents();
  await page.getByRole('group',{name:'Opportunity horizon'}).getByRole('button',{name:'SWING'}).click();
  await page.waitForFunction(()=>new URL(location.href).searchParams.get('horizon')==='SWING');
  const url=new URL(page.url());
  assert.equal(url.searchParams.get('timeframe'),'1h');
  assert.deepEqual(await page.locator('[data-source="canonical"] .qx-state').allTextContents(),statesBefore);
  assert.equal(await page.locator('[data-source="canonical"]').first().getByText('SWING · 1h',{exact:true}).count(),1);
 }finally{await browser.close();}
});

test('canonical opportunity opens Trade with the same evaluation context',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser,{horizon:'SWING'});
  const triggered=page.locator('[data-source="canonical"]').filter({hasText:'TRIGGERED'}).first();
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
  const identity=page.getByLabel('Canonical evaluation identity');
  assert.equal(await identity.getByText('1h',{exact:true}).count(),1);
  assert.equal(await identity.getByText('fixture-swing-triggered-qqq',{exact:true}).count(),1);
 }finally{await browser.close();}
});

test('explicit ETF context is preserved through canonical Trade handoff',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser,{horizon:'SWING'});
  await page.goto(`${baseUrl}/?page=opportunities&horizon=SWING&timeframe=1h&etf=SPY`);
  await page.getByRole('heading',{name:'Opportunities',exact:true}).waitFor();
  const triggered=page.locator('[data-source="canonical"]').filter({hasText:'TRIGGERED'}).first();
  await triggered.getByRole('link',{name:'Open Trade'}).click();
  await page.locator('.qx-trade-hero-state').filter({hasText:'TRIGGERED'}).waitFor();
  const url=new URL(page.url());
  assert.equal(url.searchParams.get('etf'),'SPY');
  assert.equal(url.searchParams.get('evaluation_id'),'fixture-swing-triggered-qqq');
 }finally{await browser.close();}
});

test('mobile canonical opportunity cards prioritize decision fields and retain details behind WHY',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser,{width:390,height:844});
  const row=page.locator('[data-source="canonical"]').first();
  const box=await row.boundingBox();
  assert.ok(box.height<250,`collapsed card height ${box.height}px`);
  const directChildDisplays=await row.locator(':scope > *').evaluateAll(items=>items.map(item=>getComputedStyle(item).display));
  for(const index of [3,4,6,7,9]) assert.equal(directChildDisplays[index],'none',`child ${index+1}`);
  for(const label of ['Direction','Trigger / risk','Coverage']) assert.equal(await row.getByText(label,{exact:true}).isVisible(),true,label);
  await row.getByText('WHY',{exact:true}).click();
  for(const label of ['Playbook / thesis:','Market Driver:','Tradeability:','Portfolio:','Freshness:','Provenance:']){
   assert.equal(await row.getByText(label,{exact:true}).isVisible(),true,label);
  }
 }finally{await browser.close();}
});

test('legacy discovery handoff requests a fresh canonical Trade evaluation',async()=>{
 const {createQxV2PreviewFixture}=await import(pathToFileURL(path.resolve(__dirname,'../src/qx-v2-fixtures.js')).href);
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openOpportunities(browser,{fixtures:false,horizon:'INVEST'});
  await page.route('**/api/v2/qx/evaluate/**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(createQxV2PreviewFixture('NO_SETUP','AMD'))}));
  await page.locator('[data-source="legacy"]').filter({hasText:'AMD'}).getByRole('link',{name:'Evaluate in Trade'}).click();
  await page.getByRole('heading',{name:/Trade Workspace/}).waitFor();
  const url=new URL(page.url());
  assert.equal(url.searchParams.get('symbol'),'AMD');
  assert.equal(url.searchParams.get('horizon'),'INVEST');
  assert.equal(url.searchParams.get('timeframe'),'1d');
  assert.equal(url.searchParams.has('evaluation_timestamp'),false);
  assert.equal(url.searchParams.has('evaluation_id'),false);
 }finally{await browser.close();}
});

test('Opportunities is responsive and captures review screenshots',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  for(const [label,width,height] of [['desktop',1600,1000],['laptop',1366,900],['tablet',768,1024],['mobile',390,844]]){
   const page=await openOpportunities(browser,{width,height});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label);
   await page.screenshot({path:path.join(artifactDir,`opportunities-${label}.png`),fullPage:true});
   if(label==='mobile'){
    const row=page.locator('[data-source="canonical"]').first();
    const orders=await row.locator(':scope > *').evaluateAll(items=>items.map(item=>Number(getComputedStyle(item).order)||0));
    assert.ok(orders[0]<orders[3]);
    assert.ok(orders[1]<orders[3]);
   }
   await page.close();
  }
  const empty=await openOpportunities(browser,{fixtures:false,width:1440,height:900});
  await empty.screenshot({path:path.join(artifactDir,'opportunities-canonical-empty.png'),fullPage:true});
  await empty.close();
  const why=await openOpportunities(browser,{width:1440,height:900});
  await why.locator('[data-source="canonical"]').first().getByText('WHY',{exact:true}).click();
  await why.screenshot({path:path.join(artifactDir,'opportunities-why-expanded.png'),fullPage:true});
  await why.close();
 }finally{await browser.close();}
});

test('legacy scanner routes remain available as compatibility views',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:900}});
  await page.route('**/api/**',route=>route.fulfill({contentType:'application/json',body:'{}'}));
  await page.goto(`${baseUrl}/?page=scan&symbol=SPY&horizon=DAY&timeframe=5m`);
  await page.getByText('LEGACY COMPATIBILITY VIEW',{exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'scan');
  assert.equal(await page.getByRole('navigation',{name:'Primary product navigation'}).getByRole('link',{name:'Opportunities',exact:true}).getAttribute('aria-current'),'page');
 }finally{await browser.close();}
});
