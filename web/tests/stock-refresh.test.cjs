const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
test('stock refresh is scoped to selected universe',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:900}});let posts=0,known=false,finished=false;
  await page.route('**/api/rotation/*/holdings',r=>r.fulfill({status:503,body:'{}'}));
  await page.route('**/api/stock-refresh/dow_jones',r=>{
   if(r.request().method()==='POST'){posts++;return r.fulfill({status:202,json:{status:'running'}});}
   return r.fulfill({json:{status:finished?'succeeded':posts?'running':'idle',total:known?31:0,completed:finished?31:0,...(finished?{last_success:'2026-09-10T12:00:00Z',data_as_of:'2026-09-09'}:{})}});
  });
  await page.goto('http://127.0.0.1:5173/');
  await page.getByLabel('Movers universe').selectOption('dow_jones');
  await page.getByRole('button',{name:'Refresh index prices'}).click();
  await page.getByText('Preparing histories',{exact:true}).waitFor();
  assert.equal(await page.getByText('Schwab histories: 0/32',{exact:true}).count(),0);
  known=true;
  await page.getByText('Schwab histories: 0/31',{exact:true}).waitFor();
  finished=true;
  await page.getByText(/completed session 2026-09-09/).waitFor();
  assert.equal(posts,1);
  await page.getByRole('button',{name:'Refresh index prices'}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 }finally{await browser.close();}
});
