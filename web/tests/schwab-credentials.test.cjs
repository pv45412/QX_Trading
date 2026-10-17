const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const artifactDir=path.resolve(__dirname,'../../data/reports/dq2');

test('local Schwab credential workflow renders safely',async()=>{
 fs.mkdirSync(artifactDir,{recursive:true});
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  const requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>requests.push(request.url()));
  await page.goto(`${baseUrl}/?page=schwab`);
  await page.getByText('Local Schwab Credentials',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Client Secret').getAttribute('type'),'password');
  assert.equal(await page.getByLabel('Schwab Callback URL').getAttribute('type'),'password');
  await page.getByRole('button',{name:'Save Credentials',exact:true}).waitFor();
  await page.getByRole('button',{name:'Re-authenticate Schwab',exact:true}).waitFor();
  await page.getByRole('button',{name:'Complete Authentication',exact:true}).waitFor();
  assert.equal(requests.some(url=>url.includes('/api/terminal/watchlist')),false);
  assert.deepEqual(errors,[]);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(artifactDir,'schwab-credentials-ui.png'),fullPage:true});
 }finally{await browser.close();}
});

test('local Schwab credential workflow remains accessible on mobile',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:900}});
  await page.goto(`${baseUrl}/?page=schwab`);
  await page.getByText('Local Schwab Credentials',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  for(const name of ['Warm Obsidian Eye-Comfort Theme','Mocha Dark Eye-Comfort Theme','Neutral Slate Eye-Comfort Theme','Stealth Soft Eye-Comfort Theme']){
   const box=await page.getByTitle(name).boundingBox();
   assert.ok(box&&box.x>=0&&box.x+box.width<=390,name);
  }
 }finally{await browser.close();}
});
