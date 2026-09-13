const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const path=require('node:path');
const os=require('node:os');

const react='http://127.0.0.1:5173/';
const streamlit='http://localhost:8501/';
const context={universe:'sp500',symbol:'MSFT',etf:'XLK',sector:'Information Technology',
 period:'2y',as_of:'2026-09-10',snapshot:'92'};
const rows=[['XLK','Information Technology'],['XLE','Energy'],['XLF','Financials']].map(([etf,sector])=>
 ({etf,sector,status:'CACHED_UNVERIFIED',as_of:'2026-09-10',rs_change:0.03,return_1d:0.02,excess_1d:0.01}));

async function setup(width=1440){
 const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
 const page=await browser.newPage({viewport:{width,height:1000}});
 const errors=[],writes=[],apiRequests=[];
 page.on('pageerror',error=>errors.push(error.message));
 // All API requests are local fixtures, including passive AI evidence and refresh status.
 await page.route('**/api/**',async route=>{
  const request=route.request(),pathname=new URL(request.url()).pathname;
  apiRequests.push(pathname);
  if(request.method()!=='GET'){writes.push(pathname);return route.abort();}
  let body;
  if(pathname==='/api/rotation/analytics')body={rows,coverage:3,universe:3,benchmark_metrics:{as_of:'2026-09-10',sessions:252}};
  else if(pathname.startsWith('/api/movers/'))body={rows:[],membership_status:'Fixture',membership_updated:'2026-09-10',universe:0};
  else if(pathname.endsWith('/line'))body={as_of:'2026-09-10',points:[{date:'2026-09-09',ratio:0.1},{date:'2026-09-10',ratio:0.11}],summary:{},sector_source:'fixture',benchmark_source:'fixture'};
  else if(pathname==='/api/ai/status')body={enabled:false,configured:false,message:'Disabled for navigation test'};
  else if(pathname.endsWith('/status'))body={running:false};
  else return route.fulfill({status:503,contentType:'application/json',body:'{}'});
  return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 return {browser,page,errors,writes,apiRequests};
}

function assertContext(url,expected=context){
 const query=new URL(url).searchParams;
 for(const [key,value] of Object.entries(expected))assert.equal(query.get(key),value,key);
}

async function assertLinks(page,expected=context){
 const nav=page.getByRole('navigation',{name:'Workspace pages'});
 assert.equal(await nav.locator('[aria-current="page"]').count(),1);
 assert.equal(await nav.getByRole('link',{name:'Markets',exact:true}).getAttribute('aria-current'),'page');
 for(const href of await nav.locator('a').evaluateAll(links=>links.map(link=>link.href)))assertContext(href,expected);
 const actions=page.getByRole('navigation',{name:'Selected instrument actions'});
 for(const href of await actions.locator('a').evaluateAll(links=>links.map(link=>link.href)))assertContext(href,expected);
 assertContext(await page.getByRole('link',{name:'Open report snapshot 92'}).getAttribute('href'),expected);
}

for(const width of [1440,390]){
 test(`context, chart selection and browser history remain coherent at ${width}px`,async()=>{
  const {browser,page,errors,writes}=await setup(width);
  try{
   await page.goto(`${react}?${new URLSearchParams(context)}`);
   await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
   await assertLinks(page);
   const summary=page.locator('[aria-label="Workspace context"]');
   assert.match(await summary.innerText(),/Ticker: MSFT.*ETF: XLK.*As of: 2026-09-10.*Report snapshot: 92/);
   if(width===390)await page.getByRole('combobox',{name:'Chart ETF selection'}).selectOption('XLE');
   else await page.getByRole('group',{name:'Chart ETF',exact:true}).getByRole('button',{name:'XLE',exact:true}).click();
   await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
   assertContext(page.url(),{...context,etf:'XLE'});
   await assertLinks(page,{...context,etf:'XLE'});
   await page.goBack();
   await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
   assertContext(page.url());await assertLinks(page);
   await page.goForward();
   await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
   assertContext(page.url(),{...context,etf:'XLE'});
   await page.reload();
   await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
   await assertLinks(page,{...context,etf:'XLE'});
   await page.locator('.reference-ranking .ticker').filter({hasText:'XLF'}).click();
   await page.getByRole('heading',{name:'XLF holdings',exact:true}).waitFor();
   assertContext(page.url(),{...context,symbol:'XLF',etf:'XLF'});
   await page.goBack();
   await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
   assertContext(page.url(),{...context,etf:'XLE'});
   await page.evaluate(()=>scrollTo(0,0));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:path.join(os.tmpdir(),`qx-navigation-${width}.png`)});
   assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  }finally{await browser.close();}
 });

 test(`real Streamlit Rules roundtrip preserves context and active navigation at ${width}px`,async()=>{
  const {browser,page,errors,writes}=await setup(width);
  try{
   await page.goto(`${react}?${new URLSearchParams(context)}`);
   await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
   await page.goto(`${react}?${new URLSearchParams({...context,page:'strategy_rules'})}`);
   await page.getByRole('heading',{name:'Rule Profiles',exact:true}).waitFor({timeout:45000});
   assert.equal(new URL(page.url()).origin,new URL(streamlit).origin);
   assertContext(page.url());
   const nav=page.getByRole('navigation',{name:'Workspace pages'});
   // Streamlit replaces its navigation placeholder after the page body renders.
   await nav.locator('[aria-current="page"]').waitFor();
   assert.equal(await nav.locator('[aria-current="page"]').count(),1);
   assert.equal(await nav.getByRole('link',{name:'System',exact:true}).getAttribute('aria-current'),'page');
   assert.equal(await page.getByRole('navigation',{name:'Workspace views'}).getByRole('link',{name:'Strategy Rules',exact:true}).getAttribute('aria-current'),'page');
   assert.equal(await page.locator('[data-testid="stException"]').count(),0);
   await page.screenshot({path:path.join(os.tmpdir(),`qx-navigation-streamlit-${width}.png`)});
   await nav.getByRole('link',{name:'Markets',exact:true}).click();
   await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
   assertContext(page.url());await assertLinks(page);
   await page.goBack();
   await page.getByRole('heading',{name:'Rule Profiles',exact:true}).waitFor({timeout:45000});
   assertContext(page.url());
   await page.goForward();
   await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
   assertContext(page.url());await assertLinks(page);
   assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  }finally{await browser.close();}
 });
}

test('legacy query routes forward to the correct Streamlit subview without loading analytics',async()=>{
 const {browser,page,writes,apiRequests}=await setup();
 try{
  await page.route(`${streamlit}**`,route=>route.fulfill({contentType:'text/html',body:'<h1>Destination fixture</h1>'}));
  for(const [pageKey,target,key,value] of [['qx','scan'],['automation_control','jobs','job_view','Schedule'],
   ['command_snapshots','run_history','history_view','Snapshots'],['history','run_history','history_view','Scans']]){
   await page.goto(`${react}?${new URLSearchParams({...context,page:pageKey})}`);
   await page.getByRole('heading',{name:'Destination fixture'}).waitFor();
   const url=new URL(page.url());assert.equal(url.origin,new URL(streamlit).origin);
   assert.equal(url.searchParams.get('page'),target);assertContext(url);
   if(key)assert.equal(url.searchParams.get(key),value);
  }
  assert.deepEqual(apiRequests,[]);assert.deepEqual(writes,[]);
 }finally{await browser.close();}
});

test('default chart context is shareable without an extra browser history entry',async()=>{
 const {browser,page,errors,writes}=await setup();
 try{
  await page.goto(`${react}?page=missing_view`);
  await page.getByRole('alert').waitFor();
  await page.getByRole('link',{name:'Return to Markets',exact:true}).click();
  await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
  await page.getByRole('navigation',{name:'Selected instrument actions'}).waitFor();
  assertContext(page.url(),{etf:'XLK',symbol:'XLK'});
  assertContext(await page.getByRole('navigation',{name:'Workspace pages'}).getByRole('link',{name:'Research',exact:true}).getAttribute('href'),{etf:'XLK',symbol:'XLK'});
  await page.goBack();
  await page.getByRole('alert').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'missing_view');
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 }finally{await browser.close();}
});

test('unknown routes and unavailable dates recover without dropping unrelated context',async()=>{
 const {browser,page,errors,writes,apiRequests}=await setup(390);
 try{
  const historical={...context,as_of:'2000-01-01'};
  await page.goto(`${react}?${new URLSearchParams({...historical,page:'missing_view'})}`);
  await page.getByRole('alert').waitFor();
  assert.deepEqual(apiRequests,[]);
  assert.equal(await page.getByRole('navigation',{name:'Workspace pages'}).locator('[aria-current="page"]').count(),0);
  await page.getByRole('link',{name:'Return to Markets',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'No matching relative-strength snapshot'}).waitFor();
  assertContext(page.url(),historical);await assertLinks(page,historical);
  await page.getByRole('button',{name:'Use latest session',exact:true}).click();
  await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
  assertContext(page.url(),{universe:context.universe,symbol:'MSFT',etf:'XLK',period:'2y'});
  assert.equal(new URL(page.url()).searchParams.has('as_of'),false);
  assert.equal(new URL(page.url()).searchParams.has('snapshot'),false);
  await page.goBack();
  await page.getByRole('alert').filter({hasText:'No matching relative-strength snapshot'}).waitFor();
  assertContext(page.url(),historical);await assertLinks(page,historical);
  await page.goForward();
  await page.getByRole('heading',{name:'XLK holdings',exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.has('as_of'),false);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 }finally{await browser.close();}
});
