const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
for(const width of [1440,390]) test(`manual Schwab subset ${width}`,async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width,height:1000}});
  let requests=0;
  await page.route('**/api/rotation/*/holdings',r=>r.fulfill({status:503,body:'{}'}));
  await page.route('**/api/schwab/movers',r=>{
   requests++;assert.equal(r.request().method(),'POST');
   return r.fulfill(requests===1?{json:{retrieved_at:'2026-09-10T12:00:00Z',groups:{highest:[{symbol:'TEST',last:99,return:-.01}],lowest:[]}}}:{status:503,body:'{}'});
  });
  await page.goto('http://127.0.0.1:5173/');
  const panel=page.getByRole('region',{name:'Schwab ranked movers'});
  await panel.waitFor();assert.equal(requests,0);
  await page.getByRole('button',{name:'Fetch Schwab top movers'}).click();
  await panel.getByText('-1.00%',{exact:true}).waitFor();
  assert.equal(await panel.locator('td.negative').count(),1);
  await panel.scrollIntoViewIfNeeded();await page.screenshot({path:`tests/schwab-movers-${width}.png`});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.getByRole('button',{name:'Fetch Schwab top movers'}).click();
  await panel.getByRole('alert').waitFor();
  assert.equal(await panel.getByText('-1.00%',{exact:true}).count(),1);
 }finally{await browser.close();}
});
