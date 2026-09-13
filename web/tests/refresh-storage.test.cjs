const {test}=require('node:test');
const assert=require('node:assert/strict');
const {mkdirSync}=require('node:fs');
const {chromium}=require('playwright');

const warning='Saved refresh metadata or published folder unavailable. Refresh explicitly to rebuild.';

for(const width of [390,1440])for(const stock of [false,true])test(`publication warning and explicit recovery: ${stock?'stock':'ETF'} ${width}`,async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width,height:900}});
  page.setDefaultTimeout(10000);
  const endpoint=stock?'/api/stock-refresh/sp100':'/api/refresh';
  const dataPath=stock?'/api/movers/sp100':'/api/rotation/analytics';
  let posts=0,reads=0,complete=false;const errors=[],unexpected=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(route.request().method()==='POST'){
    if(path===endpoint){posts++;return route.fulfill({status:202,json:{status:'running'}});}
    unexpected.push(path);return route.fulfill({status:403,json:{}});
   }
   if(path===endpoint)return route.fulfill({json:complete
    ?{status:'succeeded',last_success:'2026-09-10T22:00:00+00:00',data_as_of:'2026-09-10'}
    :{status:posts?'running':'idle',completed:1,total:32,storage_warning:warning}});
   if(path===dataPath)reads++;
   if(path==='/api/refresh')return route.fulfill({json:{status:'idle'}});
   if(path==='/api/ai/status')return route.fulfill({json:{enabled:false,configured:false}});
   if(path==='/api/rotation/analytics')return route.fulfill({json:{rows:[],coverage:0,universe:29,benchmark_metrics:null}});
   if(path==='/api/movers/sp100')return route.fulfill({json:{rows:[],universe:0,benchmark_metrics:null,membership_status:'Unknown membership provenance',membership_updated:'2026-09-10T22:00:00Z'}});
   return route.fulfill({status:404,json:{detail:'No saved fixture evidence'}});
  });
  await page.goto(`http://127.0.0.1:5173/${stock?'?universe=sp100':''}`);
  const button=page.getByRole('button',{name:stock?'Refresh index prices':'Refresh Now',exact:true});
  const control=page.locator('.live-refresh').nth(stock?1:0);
  await control.getByText(warning,{exact:true}).waitFor();
  assert.equal(await button.isEnabled(),true);assert.equal(posts,0);
  assert.doesNotMatch(await control.innerText(),/Refreshed /);
  await button.scrollIntoViewIfNeeded();
  mkdirSync('refresh-audit',{recursive:true});
  await page.screenshot({path:`refresh-audit/storage-${stock?'stock':'etf'}-${width}.png`});
  const before=reads;
  await button.click();
  await page.waitForResponse(r=>new URL(r.url()).pathname===endpoint&&r.request().method()==='GET');
  await control.getByText(/Schwab histories: 1\/32/).waitFor();
  assert.match(await control.innerText(),/published folder unavailable/);
  assert.equal(await control.getByRole('button').isDisabled(),true);
  assert.equal(posts,1);
  complete=true;
  await control.getByText(/completed session 2026-09-10/).waitFor();
  assert.doesNotMatch(await control.innerText(),/published folder unavailable/);
  await button.waitFor();assert.equal(await button.isEnabled(),true);
  await page.waitForFunction(()=>!document.body.innerText.includes('Loading movers...'));
  assert.ok(reads>before);assert.equal(posts,1);
  assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`refresh-audit/recovered-${stock?'stock':'etf'}-${width}.png`});
 }finally{await browser.close();}
});
