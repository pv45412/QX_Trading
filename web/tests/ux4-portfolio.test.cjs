const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/ux4/screenshots');

async function fixtures(){
 const portfolio=await import(pathToFileURL(path.resolve(__dirname,'../src/qx-portfolio-fixtures.js')).href);
 const evaluation=await import(pathToFileURL(path.resolve(__dirname,'../src/qx-v2-fixtures.js')).href);
 return {createPortfolioFixture:portfolio.createPortfolioFixture,createQxV2PreviewFixture:evaluation.createQxV2PreviewFixture};
}

async function openPortfolio(browser,{state='healthy',width=1440,height=900,horizon='DAY'}={}){
 const page=await browser.newPage({viewport:{width,height}});
 await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_portfolio_fixture_enabled:true,qx_trade_fixture_enabled:true,qx_today_fixture_enabled:true};});
 await page.goto(`${baseUrl}/?page=portfolio&horizon=${horizon}&timeframe=${horizon==='SWING'?'1h':'5m'}&portfolio_state=${state}`);
 await page.getByRole('heading',{name:'Portfolio',exact:true}).waitFor();
 return page;
}

test('Portfolio hierarchy uses canonical broker data and excludes ETF Holdings',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openPortfolio(browser);
  const headings=await page.locator('.qx-portfolio-section-title h2').allTextContents();
  assert.deepEqual(headings,['Account / Portfolio Summary','Positions','Risk & Exposure','Positions Requiring Attention','Trade / Opportunity Impact','Data Quality / Partial Evidence']);
  assert.equal(await page.getByText('TEST / PREVIEW DATA - NOT LIVE',{exact:true}).count(),1);
  assert.equal(await page.getByText('qxacct_fixture_safe_1',{exact:false}).count()>0,true);
  assert.equal(await page.locator('.holdings-table,.holdings-strength').count(),0);
  assert.equal(await page.getByText('Canonical broker positions; never ETF constituents',{exact:true}).count(),1);
  assert.equal(await page.getByText('Phase 11').count(),0);
 }finally{await browser.close();}
});

test('Portfolio review states remain explicit and never synthesize approval',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const expectations={healthy:'COMPLETE',partial:'PARTIAL',stale:'STALE',sector_unknown:'UNKNOWN',greeks_unavailable:'GREEKS UNAVAILABLE',approved:'PORTFOLIO_APPROVED',vetoed:'PORTFOLIO_VETOED',no_account:'UNAVAILABLE'};
  for(const [state,label] of Object.entries(expectations)){
   const page=await openPortfolio(browser,{state});
   assert.equal(await page.getByText(label,{exact:true}).count()>0,true,state);
   if(state==='sector_unknown') assert.equal(await page.getByText('SECTOR PROVENANCE INCOMPLETE',{exact:true}).count(),1);
   if(state==='greeks_unavailable') assert.equal(await page.getByText('GREEKS UNAVAILABLE',{exact:true}).count()>0,true);
   if(state==='no_account') assert.equal(await page.locator('.qx-position-row').count(),0);
   await page.close();
  }
 }finally{await browser.close();}
});

test('Trade links to Portfolio with stable canonical identity and no stray ETF',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_trade_fixture_enabled:true,qx_portfolio_fixture_enabled:true};});
  await page.goto(`${baseUrl}/?page=trade&symbol=NVDA&horizon=SWING&timeframe=1h&evaluation_timestamp=2026-09-16T14%3A35%3A00Z&evaluation_id=fixture-swing-approved-nvda&fixture_state=PORTFOLIO_APPROVED`);
  await page.getByRole('link',{name:'View Portfolio Impact'}).click();
  await page.getByRole('heading',{name:'Portfolio',exact:true}).waitFor();
  const url=new URL(page.url());
  assert.equal(url.searchParams.get('symbol'),'NVDA');
  assert.equal(url.searchParams.get('horizon'),'SWING');
  assert.equal(url.searchParams.get('timeframe'),'1h');
  assert.equal(url.searchParams.get('evaluation_timestamp'),'2026-09-16T14:35:00Z');
  assert.equal(url.searchParams.get('evaluation_id'),'fixture-swing-approved-nvda');
  assert.equal(url.searchParams.has('etf'),false);
  assert.equal(await page.getByText('PORTFOLIO_APPROVED',{exact:true}).count()>0,true);
 }finally{await browser.close();}
});

test('Portfolio position opens a fresh Trade evaluation without stale identity',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await openPortfolio(browser,{state:'healthy',horizon:'SWING'});
  await page.locator('.qx-position-row').filter({hasText:'AAPL'}).getByRole('link',{name:'Open Trade'}).click();
  await page.getByRole('heading',{name:/Trade Workspace/}).waitFor();
  const url=new URL(page.url());
  assert.equal(url.searchParams.get('symbol'),'AAPL');
  assert.equal(url.searchParams.get('horizon'),'SWING');
  assert.equal(url.searchParams.get('timeframe'),'1h');
  assert.equal(url.searchParams.has('evaluation_timestamp'),false);
  assert.equal(url.searchParams.has('evaluation_id'),false);
  assert.equal(url.searchParams.has('etf'),false);
 }finally{await browser.close();}
});

test('Today Portfolio link preserves attention horizon without symbol bleed',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_today_fixture_enabled:true};});
  await page.goto(`${baseUrl}/?page=today&horizon=INVEST&timeframe=1d&today_state=partial_positions`);
  await page.getByRole('heading',{name:'Positions Requiring Attention'}).waitFor();
  const href=await page.getByRole('link',{name:'Open Portfolio'}).getAttribute('href');
  const url=new URL(href,baseUrl);
  assert.equal(url.searchParams.get('horizon'),'INVEST');
  assert.equal(url.searchParams.get('timeframe'),'1d');
  assert.equal(url.searchParams.has('symbol'),false);
  assert.equal(url.searchParams.has('etf'),false);
 }finally{await browser.close();}
});

test('live Portfolio performs one account request and no implicit candidate evaluation',async()=>{
 const {createPortfolioFixture}=await fixtures();
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const requests=[];
  page.on('request',request=>{if(request.url().includes('/api/'))requests.push(`${request.method()} ${new URL(request.url()).pathname}`);});
  await page.route('**/api/v2/qx/portfolio**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(createPortfolioFixture('healthy').snapshot)}));
  await page.goto(`${baseUrl}/?page=portfolio&horizon=DAY&timeframe=5m`);
  await page.getByText('COMPLETE',{exact:true}).waitFor();
  await page.waitForTimeout(200);
  assert.equal(requests.filter(value=>value==='GET /api/v2/qx/portfolio').length,1);
  assert.equal(requests.some(value=>value.includes('/api/v2/qx/evaluate/')),false);
  assert.equal(requests.some(value=>value.includes('/api/rotation/')),false);
 }finally{await browser.close();}
});

test('Portfolio is responsive and captures approved review states',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  for(const [label,width,height] of [['desktop',1920,945],['laptop',1440,900],['tablet',768,1024],['mobile',390,844]]){
   const page=await openPortfolio(browser,{state:'healthy',width,height});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label);
   await page.screenshot({path:path.join(artifactDir,`portfolio-${label}.png`),fullPage:true});
   if(label==='mobile'){
    const visualOrder=await page.locator('.qx-portfolio-panel').evaluateAll(items=>items.map(item=>[item.querySelector('h2')?.textContent,Number(getComputedStyle(item).order)||0]));
    const order=Object.fromEntries(visualOrder);
    assert.ok(order['Positions Requiring Attention']<order.Positions);
    assert.ok(order.Positions<order['Risk & Exposure']);
   }
   await page.close();
  }
  for(const state of ['partial','stale','vetoed','no_account']){
   const page=await openPortfolio(browser,{state,width:1440,height:900});
   await page.screenshot({path:path.join(artifactDir,`portfolio-${state.replaceAll('_','-')}.png`),fullPage:true});
   await page.close();
  }
 }finally{await browser.close();}
});
