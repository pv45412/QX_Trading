const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifact=path.resolve(__dirname,'../../data/reports/track2c_frontend.json');

test('Track 2C records an observational lifecycle render baseline',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  let requestCount=0;
  page.on('request',request=>{if(request.url().includes('/api/v2/qx/evaluate/')) requestCount+=1;});
  await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_v2_ui_enabled:true};});
  const started=Date.now();
  await page.goto(`${baseUrl}/qx-v2-preview.html?state=NO_SETUP`);
  await page.locator('[aria-label="Canonical QX lifecycle"]').waitFor();
  const initialLoadMs=Date.now()-started;
  const interactions=[];
  for(const state of ['WATCH','ARMED','TRIGGERED','TRADEABLE','BLOCKED','PORTFOLIO_VETOED','PORTFOLIO_APPROVED']){
   const before=await page.evaluate(()=>performance.now());
   await page.getByLabel('Fixture state').selectOption(state);
   await page.locator('.qx-lifecycle-current .qx-state').filter({hasText:state}).waitFor();
   const after=await page.evaluate(()=>performance.now());
   interactions.push({interaction:`state:${state}`,elapsed_ms:after-before});
  }
  const switchStarted=await page.evaluate(()=>performance.now());
  await page.getByRole('button',{name:'QQQ',exact:true}).click();
  await page.locator('.qx-lifecycle-identity').getByText('QQQ',{exact:true}).waitFor();
  const switchEnded=await page.evaluate(()=>performance.now());
  interactions.push({interaction:'symbol:SPY->QQQ',elapsed_ms:switchEnded-switchStarted});
  const browserMetrics=await page.evaluate(()=>({
   navigation:performance.getEntriesByType('navigation').map(entry=>({
    duration_ms:entry.duration,
    dom_content_loaded_ms:entry.domContentLoadedEventEnd,
    load_event_ms:entry.loadEventEnd,
   })),
   lifecycle_renders:globalThis.__QX_PERFORMANCE__?.lifecycleRenders||[],
   v2_api_ms:globalThis.__QX_PERFORMANCE__?.v2ApiMs||[],
   memory:performance.memory?{
    used_js_heap_size:performance.memory.usedJSHeapSize,
    total_js_heap_size:performance.memory.totalJSHeapSize,
   }:null,
  }));
  const payload={
   status:'MEASURED_FIXTURE_RENDER_ONLY',
   measured_at:new Date().toISOString(),
   initial_load_wall_ms:initialLoadMs,
   interactions,
   canonical_api_request_count:requestCount,
   frontend_evaluation_latency_status:'UNAVAILABLE_IN_ISOLATED_PREVIEW',
   scanner_refresh:{status:'UNAVAILABLE_IN_ISOLATED_LIFECYCLE_PREVIEW'},
   chart_redraw_count:{status:'UNAVAILABLE_NO_CHART_IN_LIFECYCLE_PREVIEW'},
   polling:{status:'NOT_PRESENT',observation_window_ms:0,observed_request_count:0},
   ...browserMetrics,
  };
  fs.mkdirSync(path.dirname(artifact),{recursive:true});
  fs.writeFileSync(artifact,JSON.stringify(payload,null,2));
  assert.ok(Number.isFinite(initialLoadMs));
  assert.ok(interactions.every(item=>Number.isFinite(item.elapsed_ms)));
  assert.ok(browserMetrics.lifecycle_renders.length>0);
 }finally{await browser.close();}
});

test('Track 2C records real browser-to-V2 evaluation latency when enabled',{
 skip:process.env.QX_LIVE_BASELINE!=='1',
},async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const requests=[];
  page.on('request',request=>{
   if(request.url().includes('/api/v2/qx/evaluate/')) requests.push(request.url());
  });
  await page.goto(`${baseUrl}/qx-v2-live-baseline.html`);
  await page.locator('[aria-label="Canonical QX lifecycle"]').waitFor();
  await page.waitForFunction(()=>globalThis.__QX_PERFORMANCE__?.v2ApiMs?.length>=1);
  await page.getByRole('button',{name:'QQQ',exact:true}).click();
  await page.waitForFunction(()=>globalThis.__QX_PERFORMANCE__?.v2ApiMs?.length>=2);
  const requestsBeforeSettle=requests.length;
  await page.waitForTimeout(1000);
  const requestsAfterSettle=requests.length-requestsBeforeSettle;
  const metrics=await page.evaluate(()=>({
   v2_api_ms:globalThis.__QX_PERFORMANCE__?.v2ApiMs||[],
   lifecycle_renders:globalThis.__QX_PERFORMANCE__?.lifecycleRenders||[],
  }));
  const bySymbol=Object.fromEntries(['SPY','QQQ'].map(symbol=>[
   symbol,
   requests.filter(url=>url.includes(`/evaluate/${symbol}`)).length,
  ]));
  const existing=fs.existsSync(artifact)?JSON.parse(fs.readFileSync(artifact,'utf8')):{};
  fs.writeFileSync(artifact,JSON.stringify({
   ...existing,
   status:'MEASURED_FIXTURE_AND_LIVE_V2',
   frontend_evaluation_latency_status:'MEASURED_BROWSER_TO_LOCAL_V2',
   v2_api_ms:metrics.v2_api_ms,
   live_lifecycle_renders:metrics.lifecycle_renders,
   live_canonical_api_request_count:requests.length,
   duplicate_api_calls_by_symbol:bySymbol,
   polling:{
    status:'OBSERVED_NO_POLLING',
    observation_window_ms:1000,
    observed_request_count_after_settle:requestsAfterSettle,
   },
   scanner_refresh:{status:'UNAVAILABLE_NOT_PRESENT_IN_V2_LIFECYCLE_HARNESS'},
   chart_redraw_count:{status:'UNAVAILABLE_NO_CHART_IN_V2_LIFECYCLE_HARNESS'},
  },null,2));
  assert.equal(bySymbol.SPY,1);
  assert.equal(bySymbol.QQQ,1);
  assert.equal(metrics.v2_api_ms.length,2);
  assert.equal(requestsAfterSettle,0);
 }finally{await browser.close();}
});
