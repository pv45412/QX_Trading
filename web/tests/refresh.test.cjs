const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');

test('manual refresh starts once and reloads analytics on success',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:900},timezoneId:'America/Los_Angeles'});
  let posts=0,reads=0;
  await page.route('**/api/refresh',route=>{
   if(route.request().method()==='POST'){posts++;return route.fulfill({status:202,json:{status:'running'}});}
   return route.fulfill({json:posts?{status:'succeeded',last_success:'2026-09-10T12:00:00Z',data_as_of:'2026-09-09'}:{status:'idle'}});
  });
  await page.route('**/api/rotation/*/holdings',r=>r.fulfill({status:503,json:{}}));
  page.on('request',r=>{if(r.url().endsWith('/api/rotation/analytics'))reads++;});
  await page.goto('http://127.0.0.1:5173/');
  await page.locator('.reference-ranking tbody tr').first().waitFor();
  const before=reads;
  await page.getByRole('button',{name:'Refresh Now',exact:true}).click();
  await page.getByText(/completed session 2026-09-09/).waitFor();
  assert.match(await page.locator('.live-refresh').innerText(),/Sep 10, 2026, 08:00 AM EDT/);
  assert.equal(posts,1);assert.ok(reads>before);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'refresh-mobile.png'});
 }finally{await browser.close();}
});

for(const status of [409,503])test(`refresh rejection ${status} stays visible after polling without retry`,async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:900}});let posts=0;
  await page.route('**/api/refresh',route=>{
   if(route.request().method()==='POST'){posts++;return route.fulfill({status,json:{detail:'Rejected'}});}
   return route.fulfill({json:{status:'idle'}});
  });
  await page.route('**/api/rotation/*/holdings',r=>r.fulfill({status:503,json:{}}));
  await page.goto('http://127.0.0.1:5173/');
  const button=page.getByRole('button',{name:'Refresh Now',exact:true});
  await button.waitFor();assert.equal(posts,0);
  await button.click();
  const message=status===409?'Another refresh was already running. No additional job started.':'Refresh service unavailable. No work started.';
  await page.getByText(message,{exact:true}).waitFor();
  await page.waitForResponse(r=>r.url().endsWith('/api/refresh')&&r.request().method()==='GET');
  await page.waitForTimeout(300);
  assert.equal(await page.getByText(message,{exact:true}).count(),1);
  assert.equal(await button.isEnabled(),true);assert.equal(posts,1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 }finally{await browser.close();}
});
