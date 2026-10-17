const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/ux6/screenshots');

async function fixtureModule(){return import(pathToFileURL(path.resolve(__dirname,'../src/qx-system-fixtures.js')).href);}

async function mockSystem(page){
 const fixtures=await fixtureModule();
 await page.addInitScript(()=>{window.__QX_FEATURE_FLAGS__={qx_system_fixture_enabled:true};});
 await page.route('**/api/system/overview',route=>route.fulfill({json:fixtures.systemOverviewFixture()}));
 await page.route('**/api/system/jobs/status',route=>route.fulfill({json:fixtures.systemJobFixture()}));
 await page.route('**/api/system/schwab/credentials/status',route=>route.fulfill({json:fixtures.systemSchwabFixture()}));
 await page.route('**/api/system/schwab/**',route=>route.fulfill({json:fixtures.systemSchwabFixture()}));
}

async function openSystem(browser,{pageName='system',width=1440,height=900}={}){
 const page=await browser.newPage({viewport:{width,height}});await mockSystem(page);
 await page.goto(`${baseUrl}/?page=${pageName}&symbol=SPY&horizon=DAY&timeframe=5m&system_fixture=1`);
 await page.getByLabel('System workspace').waitFor();return page;
}

test('System is one truthful read-only operational workspace',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openSystem(browser);
  await page.getByText('TEST / PREVIEW DATA - NOT LIVE',{exact:true}).waitFor();
  assert.equal(await page.getByText('core_v1',{exact:true}).count()>0,true);
  assert.equal(await page.getByText('UNVERIFIED',{exact:true}).count()>0,true);
  assert.equal(await page.getByRole('button',{name:/Execute|Trade|Submit order/i}).count(),0);
  assert.deepEqual(await page.getByRole('navigation',{name:'System views'}).getByRole('button').allTextContents(),['Overview','Providers','Data','Jobs','Runs','Rules']);
 }finally{await browser.close();}
});

test('legacy System routes remain clearly labeled compatibility aliases',async()=>{
 const browser=await chromium.launch({headless:true});try{
  for(const [route,tab] of [['schwab','Providers'],['data_cache','Data'],['jobs','Jobs'],['run_history','Runs'],['strategy_rules','Rules']]){
   const page=await openSystem(browser,{pageName:route});
   assert.equal(await page.getByText('LEGACY COMPATIBILITY VIEW',{exact:true}).count(),1,route);
   assert.equal(await page.getByRole('button',{name:tab,exact:true}).getAttribute('aria-pressed'),'true',route);
   await page.close();
  }
 }finally{await browser.close();}
});

test('Providers preserves masked credential and callback controls without rendering secrets',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await openSystem(browser,{pageName:'schwab'});
  await page.getByText('Local Schwab Credentials',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Client Secret').getAttribute('type'),'password');
  assert.equal(await page.getByLabel('Schwab Callback URL').getAttribute('type'),'password');
  assert.equal(await page.getByText('AUTHENTICATED',{exact:true}).count(),1);
  assert.equal(await page.content().then(content=>content.includes('client_secret')||content.includes('access_token')||content.includes('refresh_token')),false);
 }finally{await browser.close();}
});

test('System tabs isolate optional API requests',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage({viewport:{width:1440,height:900}});await mockSystem(page);const paths=[];
  page.on('request',request=>{const pathname=new URL(request.url()).pathname;if(pathname.startsWith('/api/'))paths.push(pathname);});
  await page.goto(`${baseUrl}/?page=system&system_fixture=1`);await page.getByLabel('System overview').waitFor();
  assert.equal(paths.filter(value=>value==='/api/system/overview').length,1);
  assert.equal(paths.includes('/api/system/jobs/status'),false);assert.equal(paths.includes('/api/system/schwab/credentials/status'),false);
  await page.getByRole('button',{name:'Jobs',exact:true}).click();await page.getByLabel('Jobs status').waitFor();
  assert.equal(paths.filter(value=>value==='/api/system/jobs/status').length,1);
  await page.getByRole('button',{name:'Providers',exact:true}).click();await page.getByText('Local Schwab Credentials',{exact:true}).waitFor();
  assert.equal(paths.filter(value=>value==='/api/system/schwab/credentials/status').length,1);
 }finally{await browser.close();}
});

test('System remains responsive and captures each approved operational view',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});const browser=await chromium.launch({headless:true});try{
  for(const [label,width,height] of [['desktop',1920,945],['laptop',1440,900],['mobile',390,844]]){
   const page=await openSystem(browser,{width,height});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label);
   await page.screenshot({path:path.join(artifactDir,`system-${label}.png`),fullPage:true});await page.close();
  }
  for(const [route,label] of [['system','overview'],['schwab','providers'],['data_cache','data'],['jobs','jobs'],['run_history','runs'],['strategy_rules','rules']]){
   const page=await openSystem(browser,{pageName:route});
   if(route==='jobs')await page.getByText('Success',{exact:true}).waitFor();
   if(route==='schwab')await page.getByText('AUTHENTICATED',{exact:true}).waitFor();
   await page.screenshot({path:path.join(artifactDir,`system-${label}.png`),fullPage:true});await page.close();
  }
 }finally{await browser.close();}
});
