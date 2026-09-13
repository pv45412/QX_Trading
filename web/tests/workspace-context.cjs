const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const settle=async p=>{await p.locator('.qx-page-header').waitFor({timeout:45000});await p.waitForFunction(()=>!document.querySelector('[data-testid="stApp"][data-test-script-state="running"]'),{},{timeout:45000});await p.waitForTimeout(800);assert.equal(await p.locator('[data-testid="stException"]').count(),0);};

(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 fs.mkdirSync('navigation-audit',{recursive:true});
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const context='universe=sp500&symbol=MSFT&etf=XLK&period=2y';
  const destinations=[['Today','command_center'],['Scanner','scan'],['Research','ticker_history'],['Journal','idea_tracking'],['System','data_cache']];
  for(const [label,route] of destinations){
   await page.goto(`http://127.0.0.1:5173/?${context}`);
   await page.getByRole('navigation',{name:'Workspace pages'}).getByRole('link',{name:label,exact:true}).click();
   await settle(page);
   assert.equal(new URL(page.url()).searchParams.get('page'),route);
   const nav=page.getByRole('navigation',{name:'Workspace pages'});
   assert.equal(await nav.getByRole('link',{name:label,exact:true}).getAttribute('aria-current'),'page');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(route==='ticker_history')assert.equal(await page.getByRole('textbox',{name:'Ticker',exact:true}).inputValue(),'MSFT');
   await page.screenshot({path:`navigation-audit/${width}-${route}.png`});
   await nav.getByRole('link',{name:'Markets',exact:true}).click();
   await page.getByRole('heading',{name:'Relative Strength Dashboard'}).waitFor();
   assert.equal(new URL(page.url()).searchParams.get('universe'),'sp500');
   console.log(`${width}: ${label} roundtrip passed`);
  }
  await page.goto(`http://localhost:8501/?page=command_center&${context}`);await settle(page);
  const id=new URL(page.url()).searchParams.get('snapshot');assert.ok(id);
  await page.getByRole('navigation',{name:'Workspace views'}).getByRole('link',{name:'Changes',exact:true}).click();await settle(page);
  assert.equal(new URL(page.url()).searchParams.get('snapshot'),id);
  await page.getByRole('navigation',{name:'Workspace views'}).getByRole('link',{name:'Preparation',exact:true}).click();await settle(page);
  assert.equal(new URL(page.url()).searchParams.get('snapshot'),id);
  await page.goBack();await settle(page);assert.equal(new URL(page.url()).searchParams.get('page'),'morning_report');
  await page.goForward();await settle(page);assert.equal(new URL(page.url()).searchParams.get('page'),'daily_workflow');
  await page.goto(`http://127.0.0.1:5173/?${context}&as_of=2000-01-01`);
  await page.getByRole('alert').filter({hasText:'No matching relative-strength snapshot'}).waitFor({timeout:30000});
  assert.equal(await page.getByRole('heading',{name:'Sector Ranking',exact:true}).count(),0);
  await page.getByRole('navigation',{name:'Workspace pages'}).getByRole('link',{name:'Scanner',exact:true}).click();await settle(page);
  assert.equal(new URL(page.url()).searchParams.get('as_of'),'2000-01-01');
  assert.equal(await page.getByRole('button',{name:'Run Scan',exact:true}).isDisabled(),true);
  await page.screenshot({path:`navigation-audit/${width}-historical.png`});
  assert.deepEqual(errors,[]);await page.close();
 }}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
