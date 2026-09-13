const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {chromium}=require('playwright');

// Only Vite's local modules/styles are allowed through; every API is a fixture.
const base=process.env.HOLDINGS_TEST_URL||'http://127.0.0.1:5173';
const html=`<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/src/style.css"><link rel="stylesheet" href="/src/dashboard.css"></head>
<body><main id="root"></main><script type="module">
import React from '/node_modules/.vite/deps/react.js';
import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
import Holdings from '/src/Holdings.jsx';
function Fixture(){const [symbol,setSymbol]=React.useState('XLK');return React.createElement(React.Fragment,null,
 React.createElement('select',{'aria-label':'Fixture ETF',value:symbol,onChange:e=>setSymbol(e.target.value)},
  ['XLK','XLE'].map(value=>React.createElement('option',{key:value,value},value))),
 React.createElement(Holdings,{symbol}));}
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Fixture));
</script></body></html>`;
const saved=(symbol='XLK')=>({symbol,source:'Yahoo Finance fund data',
 retrieved_at:'2025-01-01T13:00:00+00:00',holdings_as_of:null,
 holdings_status:'SAVED_UNVERIFIED',stale_holdings:true,refresh_error:null,analytics_coverage:0,
 rows:[{symbol:symbol==='XLK'?'AAPL':'XOM',name:symbol==='XLK'?'Apple':'Exxon Mobil',weight:.2},
  {symbol:symbol==='XLK'?'MSFT':'CVX',name:symbol==='XLK'?'Microsoft':'Chevron',weight:.15},
  {symbol:symbol==='XLK'?'NVDA':'COP',name:symbol==='XLK'?'Nvidia':'ConocoPhillips',weight:.1}]});

async function fixture(t,width=1440){
 const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
 t.after(()=>browser.close());
 const context=await browser.newContext({viewport:{width,height:1000},serviceWorkers:'block'});
 const page=await context.newPage(),errors=[],unexpected=[],requests=[];
 const state={get:async(route,symbol)=>route.fulfill({json:saved(symbol)}),post:null};
 page.on('pageerror',error=>errors.push(error.message));
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==new URL(base).origin){unexpected.push(request.url());return route.abort();}
  if(url.pathname==='/__holdings_fixture__')return route.fulfill({contentType:'text/html',body:html});
  if(url.pathname.startsWith('/api/')){
   const match=url.pathname.match(/^\/api\/rotation\/([A-Z]+)\/holdings(\/refresh)?$/);
   requests.push({path:url.pathname,method:request.method(),headers:request.headers()});
   if(match&&!match[2]&&request.method()==='GET')return state.get(route,match[1]);
   if(match&&match[2]&&request.method()==='POST'&&state.post)return state.post(route,match[1]);
   unexpected.push(`${request.method()} ${url.pathname}`);return route.abort();
  }
  if(['/src/','/node_modules/','/@vite/'].some(prefix=>url.pathname.startsWith(prefix)))return route.continue();
  if(url.pathname==='/favicon.ico')return route.fulfill({status:204});
  unexpected.push(url.pathname);return route.abort();
 });
 t.after(()=>{assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);});
 return {page,state,requests,open:()=>page.goto(`${base}/__holdings_fixture__`)};
}
const posts=requests=>requests.filter(request=>request.method==='POST');
const rows=page=>page.locator('#holdings tbody');
const refresh=page=>page.getByRole('button',{name:'Refresh fund holdings',exact:true});

for(const width of [1440,390])test(`saved holdings stay passive and refresh once at ${width}px`,async t=>{
 const {page,state,requests,open}=await fixture(t,width);
 let pending;
 state.post=route=>{pending=route;};
 await open();
 await page.getByText('Saved holdings; freshness unverified. Weights may have changed.',{exact:true}).waitFor();
 assert.equal(posts(requests).length,0);
 assert.doesNotMatch(await page.locator('#holdings').innerText(),/provider unavailable|refresh failed/i);
 await page.getByRole('button',{name:'Portfolio weights',exact:true}).click();
 assert.match(await rows(page).innerText(),/AAPL/);
 assert.match(await page.locator('.concentration').innerText(),/45.00%/);
 const original=await page.locator('#holdings .status').innerText();
 assert.match(original,/2025.*E[SD]T/);
 assert.match(original,/holdings effective date unavailable/);
 await refresh(page).focus();
 await page.keyboard.press('Enter');
 await page.getByText('Refreshing fund holdings...',{exact:true}).waitFor();
 assert.equal(await refresh(page).isDisabled(),true);
 assert.equal(await refresh(page).getAttribute('aria-busy'),'true');
 await refresh(page).evaluate(button=>{button.click();button.click();});
 assert.equal(posts(requests).length,1);
 assert.equal(posts(requests)[0].headers['x-qx-refresh'],'1');
 assert.equal(await page.locator('#holdings .status').innerText(),original);
 assert.match(await rows(page).innerText(),/AAPL/);
 const next={...saved(),retrieved_at:'2025-02-01T13:00:00+00:00',stale_holdings:false,
  holdings_status:'REFRESHED',rows:[{symbol:'AVGO',name:'Broadcom',weight:.25}]};
 await pending.fulfill({json:next});
 await page.getByText('Holdings refreshed and saved.',{exact:true}).waitFor();
 assert.match(await rows(page).innerText(),/AVGO/);
 assert.doesNotMatch(await rows(page).innerText(),/AAPL/);
 assert.equal(posts(requests).length,1);
 assert.equal(await refresh(page).isEnabled(),true);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 const screenshotDir=path.join(os.tmpdir(),'qx-holdings-passive');
 await fs.mkdir(screenshotDir,{recursive:true});
 await page.screenshot({path:path.join(screenshotDir,`holdings-${width}.png`),fullPage:true});
});

for(const fallback of [false,true])test(`failed explicit refresh retains holdings (${fallback?'saved fallback':'HTTP error'})`,async t=>{
 const {page,state,requests,open}=await fixture(t);
 state.post=route=>route.fulfill(fallback?{json:{...saved(),refresh_error:
  'Holdings refresh failed. Showing saved holdings; weights may have changed.'}}:{status:503,json:{detail:'Unavailable'}});
 await open();await rows(page).waitFor();
 const originalRows=await rows(page).innerText(),originalTime=await page.locator('#holdings .status').innerText();
 await refresh(page).click();
 await page.getByRole('alert').waitFor();
 assert.match(await page.getByRole('alert').innerText(),/refresh failed/);
 assert.equal(await rows(page).innerText(),originalRows);
 assert.equal(await page.locator('#holdings .status').innerText(),originalTime);
 assert.equal(posts(requests).length,1);
 assert.equal(await refresh(page).isEnabled(),true);
});

for(const kind of ['missing','wrong symbol','corrupt'])test(`${kind} initial data is never presented as compatible`,async t=>{
 const {page,state,requests,open}=await fixture(t);
 state.get=route=>route.fulfill(kind==='missing'?{status:404,json:{}}:{json:kind==='wrong symbol'?saved('XLE'):{...saved(),rows:[]}});
 await open();await page.getByRole('button',{name:'Retry holdings',exact:true}).waitFor();
 assert.equal(await rows(page).count(),0);
 assert.equal(posts(requests).length,0);
 assert.doesNotMatch(await page.locator('#holdings').innerText(),/provider unavailable|refresh failed|XOM/);
 await page.getByRole('button',{name:'Retry holdings',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('[aria-label="Refresh fund holdings"]').disabled);
 assert.equal(posts(requests).length,0);
 assert.equal(requests.filter(request=>request.method==='GET').length,2);
 state.post=route=>route.fulfill({json:{...saved(),stale_holdings:false,holdings_status:'REFRESHED'}});
 await refresh(page).click();await rows(page).waitFor();
 assert.equal(posts(requests).length,1);
 assert.match(await rows(page).innerText(),/AAPL/);
});

for(const phase of ['GET','POST'])test(`ETF selection aborts a pending ${phase} and ignores the old result`,async t=>{
 const {page,state,requests,open}=await fixture(t,390);
 let pending,aborted=false;
 page.on('requestfailed',request=>{if(request.url().includes('/XLK/holdings')&&request.method()===phase)aborted=true;});
 if(phase==='GET')state.get=(route,symbol)=>symbol==='XLK'?(pending=route,undefined):route.fulfill({json:saved(symbol)});
 else state.post=route=>{pending=route;};
 await open();
 if(phase==='POST'){await rows(page).waitFor();await refresh(page).click();}
 await page.waitForFunction(()=>document.querySelector('[aria-label="Refresh fund holdings"]').disabled);
 await page.getByLabel('Fixture ETF').selectOption('XLE');
 await page.getByRole('heading',{name:'XLE holdings',exact:true}).waitFor();
 await rows(page).waitFor();
 assert.match(await rows(page).innerText(),/XOM/);
 await pending.fulfill({json:saved('XLK')}).catch(()=>{});
 assert.equal(aborted,true);
 assert.doesNotMatch(await rows(page).innerText(),/AAPL/);
 assert.equal(await refresh(page).isEnabled(),true);
 assert.equal(posts(requests).length,phase==='POST'?1:0);
});

test('refresh timeout releases pending state without clearing prior holdings or retrying',async t=>{
 const {page,state,requests,open}=await fixture(t);
 state.post=()=>{};
 await page.clock.install();await open();await rows(page).waitFor();
 const original=await rows(page).innerText();
 await refresh(page).click();await page.getByText('Refreshing fund holdings...',{exact:true}).waitFor();
 await page.clock.fastForward(15001);
 await page.getByRole('alert').waitFor();
 assert.match(await page.getByRole('alert').innerText(),/refresh timed out/);
 assert.equal(await rows(page).innerText(),original);
 assert.equal(await refresh(page).isEnabled(),true);
 assert.equal(posts(requests).length,1);
});
