const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const states=['NO_SETUP','WATCH','ARMED','TRIGGERED','TRADEABLE','BLOCKED','PORTFOLIO_VETOED','PORTFOLIO_APPROVED'];
const artifactDir=path.resolve(__dirname,'../../data/reports/track2f');

async function previewPage(browser,{enabled=true,width=1440,state='NO_SETUP'}={}){
 const page=await browser.newPage({viewport:{width,height:1000}});
 await page.addInitScript(flag=>{window.__QX_FEATURE_FLAGS__={qx_v2_ui_enabled:flag};},enabled);
 await page.goto(`${baseUrl}/qx-v2-preview.html?state=${state}`);
 return page;
}

test('Track 2F feature flag defaults off and hides lifecycle panel',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await previewPage(browser,{enabled:false});
  await page.getByText('QX V2 UI feature flag is OFF.',{exact:true}).waitFor();
  assert.equal(await page.locator('[aria-label="Canonical QX lifecycle"]').count(),0);
 }finally{await browser.close();}
});

test('Track 2F feature flag on renders every approved fixture state',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  const page=await previewPage(browser,{state:states[0]});
  await page.getByText('TEST / PREVIEW DATA — NOT LIVE',{exact:true}).waitFor();
  for(const state of states){
   await page.getByLabel('Fixture state').selectOption(state);
   await page.locator('.qx-lifecycle-current .qx-state').filter({hasText:state}).waitFor();
   assert.equal(await page.locator('.qx-lifecycle-current .qx-state').innerText(),state);
   await page.screenshot({path:path.join(artifactDir,`${state.toLowerCase()}.png`),fullPage:true});
  }
 }finally{await browser.close();}
});

test('Track 2F WHY expands and preserves structured trigger evidence fields',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await previewPage(browser,{state:'TRIGGERED'});
  const why=page.locator('.qx-lifecycle-why');
  assert.equal(await why.getAttribute('open'),null);
  await why.locator('summary').click();
  assert.notEqual(await why.getAttribute('open'),null);
  await page.getByRole('region',{name:'TRIGGER evidence'}).waitFor();
  for(const label of ['Rule version','Category','Required','Observed','Severity','Hard gate','Weight','Contribution','Provenance','Event timestamp','Knowledge timestamp','Detail']){
   assert.ok(await page.getByText(label,{exact:true}).count()>0,label);
  }
  await why.locator('summary').click();
  assert.equal(await why.getAttribute('open'),null);
 }finally{await browser.close();}
});

test('Track 2F blocked and armed states remain semantically distinct',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await previewPage(browser,{state:'BLOCKED'});
  await page.getByText('Evaluation cannot proceed with the available canonical evidence.',{exact:true}).first().waitFor();
  const triggerStage=page.locator('.qx-stage-availability li').filter({hasText:'Trigger'}).first();
  assert.match(await triggerStage.innerText(),/BLOCKED/);
  await page.getByLabel('Fixture state').selectOption('ARMED');
  await page.locator('.qx-lifecycle-current .qx-state').filter({hasText:'ARMED'}).waitFor();
  assert.equal(await page.getByText('UNCONFIRMED',{exact:true}).count(),1);
  assert.equal(await page.getByText('Trigger confirmed.',{exact:true}).count(),0);
 }finally{await browser.close();}
});

test('Track 2F symbol switching replaces prior fixture identity',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await previewPage(browser,{state:'TRIGGERED'});
  const identity=page.locator('.qx-lifecycle-identity');
  await identity.getByText('SPY',{exact:true}).waitFor();
  await page.getByRole('button',{name:'QQQ',exact:true}).click();
  await identity.getByText('QQQ',{exact:true}).waitFor();
  assert.equal(await identity.getByText('SPY',{exact:true}).count(),0);
 }finally{await browser.close();}
});

for(const width of [1024,768,390]){
 test(`Track 2F lifecycle panel has no horizontal overflow at ${width}px`,async()=>{
  const browser=await chromium.launch({headless:true});
  try{
   const page=await previewPage(browser,{state:'PORTFOLIO_APPROVED',width});
   await page.locator('[aria-label="Canonical QX lifecycle"]').waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  }finally{await browser.close();}
 });
}
