const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 fs.mkdirSync('today-ai-audit',{recursive:true});
 try {
  for(const width of [1440,390]) {
   const context=await browser.newContext({viewport:{width,height:1000}});
   const errors=[],generationRequests=[];
   context.on('page',page=>page.on('pageerror',error=>errors.push(error.message)));
   context.on('request',request=>{
    if(request.method()==='POST'&&request.url().includes('/api/ai/review/'))generationRequests.push(request.url());
   });
   const status=await context.request.get('http://127.0.0.1:8510/api/ai/status');
   assert.equal((await status.json()).enabled,false,'Live AI must stay disabled');
   const page=await context.newPage();
   await page.goto('http://localhost:8501/?page=command_center');
   await page.getByText('AI evidence review',{exact:true}).click({timeout:60000});
   await page.getByRole('combobox',{name:/ETF$/}).click();
   await page.getByRole('option',{name:'XLE | Energy',exact:true}).click();
   await page.getByRole('button',{name:'Check evidence',exact:false}).click();
   await page.getByText('Disabled',{exact:true}).waitFor({timeout:30000});
   assert.equal(await page.locator('[data-testid="stException"]').count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   const link=page.getByRole('link',{name:'Open AI review',exact:false});
   const destination=new URL(await link.getAttribute('href'));
   assert.equal(destination.origin,'http://127.0.0.1:5173');
   assert.equal(destination.searchParams.get('etf'),'XLE');
   assert.equal(destination.hash,'#ai-review');
   const todayContext=new URL(page.url()).searchParams;
   for(const key of ['universe','period','snapshot']) {
    assert.equal(destination.searchParams.get(key),todayContext.get(key),`${key} must survive AI navigation`);
   }
   await page.screenshot({path:`today-ai-audit/${width}-today.png`,fullPage:true});
   const popupReady=page.waitForEvent('popup');
   await link.click();
   const review=await popupReady;
   await review.getByRole('button',{name:'Generate AI review',exact:true}).waitFor({timeout:60000});
   assert.equal(await review.getByRole('button',{name:'Generate AI review',exact:true}).isDisabled(),true);
   await review.getByText('Live AI is disabled on this server.',{exact:true}).waitFor();
   const evidence=await (await context.request.get('http://127.0.0.1:8510/api/ai/evidence/XLE')).json();
   if(!evidence.validation.live_eligible){
    await review.getByText(`Evidence: ${evidence.validation.status}`,{exact:true}).waitFor();
    assert.equal(await review.getByText('Evidence check expired. Reload before generating a review.',{exact:true}).count(),0);
    if(!evidence.facts.bar_date)await review.getByText('Daily session: Unavailable',{exact:true}).waitFor();
   }
   assert.equal(new URL(review.url()).searchParams.get('etf'),'XLE');
   assert.match(await review.locator('#ai-review h2').innerText(),/XLE/);
   await review.waitForLoadState('networkidle');
   await review.waitForFunction(()=>{
    const rect=document.getElementById('ai-review')?.getBoundingClientRect();
    const nav=document.querySelector('.section-nav')?.getBoundingClientRect();
    return rect&&nav&&rect.top>=nav.bottom&&rect.top<180;
   },null,{timeout:10000});
   assert.equal(await review.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await review.screenshot({path:`today-ai-audit/${width}-review.png`});
   await review.mouse.wheel(0,-450);
   await review.waitForTimeout(300);
   const afterScroll=await review.evaluate(()=>scrollY);
   await review.evaluate(()=>{document.querySelector('main').style.paddingTop='100px';});
   await review.waitForTimeout(300);
   assert.ok(Math.abs(await review.evaluate(()=>scrollY)-afterScroll)<150,'Initial anchor must release after user scroll');
   assert.deepEqual(generationRequests,[]);
   assert.deepEqual(errors,[]);
   console.log(`${width}: Today evidence check, XLE deep link, disabled AI, layout and no generation requests passed`);
   await context.close();
  }
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
