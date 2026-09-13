const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 fs.mkdirSync('ai-audit',{recursive:true});
 try{
  for(const width of [1440,390]){
   const p=await browser.newPage({viewport:{width,height:1000}});
   const errors=[];p.on('pageerror',e=>errors.push(e.message));
   let enabled=false,stale=false,posts=0;
   const evidence={schema_version:'qx.rs-review.v2',validation:{live_eligible:true,status:'verified_completed_daily',issues:[]},snapshot_id:'a'.repeat(64),expires_at:new Date(Date.now()+300000).toISOString(),
    facts:{symbol:'XLK',bar_date:'2026-09-10',sources:{XLK:{actual_source:'schwab'},SPY:{actual_source:'schwab'}}},
    limitations:['Completed daily context, not a trade recommendation.']};
   await p.route('**/api/rotation/*/holdings',r=>r.fulfill({status:503,json:{}}));
   await p.route('**/api/ai/**',async r=>{
    if(r.request().url().endsWith('/status'))return r.fulfill({json:{enabled,configured:enabled,message:enabled?'Mock API configured.':'Live AI is disabled on this server.'}});
    if(r.request().method()==='GET')return stale?r.fulfill({status:409,json:{detail:'Fresh evidence required. Refresh ETF prices and retry.'}}):r.fulfill({json:evidence});
    posts++;assert.deepEqual(r.request().postDataJSON(),{snapshot_id:evidence.snapshot_id});
    assert.equal(r.request().headers()['x-qx-ai'],'1');
    return r.fulfill({json:{...evidence,observations:[{id:'relative_strength',text:'Verified observation from snapshot.',fields:['rs_change']}],checks:[{id:'events',text:'Check missing calendar evidence.'}]}});
   });
   await p.goto('http://127.0.0.1:5173/');
   const panel=p.getByRole('region',{name:'AI evidence review'});
   await panel.getByText('Live AI is disabled on this server.',{exact:true}).waitFor();
   const button=panel.getByRole('button',{name:'Generate AI review'});
   assert.equal(await button.isDisabled(),true);assert.equal(posts,0);
   await panel.scrollIntoViewIfNeeded();
   await p.screenshot({path:`ai-audit/${width}-disabled.png`});
   enabled=true;
   await panel.getByRole('button',{name:'Reload AI evidence'}).click();
   await panel.getByText('Mock API configured.',{exact:true}).waitFor();
   await button.click();
   await panel.getByText('Verified observation from snapshot.').waitFor();
   assert.equal(posts,1);
   await panel.getByText('Evidence & limitations',{exact:true}).click();
   await p.screenshot({path:`ai-audit/${width}-review.png`});
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   stale=true;
   await panel.getByRole('button',{name:'Reload AI evidence'}).click();
   await panel.getByText('Fresh evidence required. Refresh ETF prices and retry.',{exact:true}).waitFor();
   assert.equal(await panel.getByText('Verified observation from snapshot.').count(),0);
   assert.equal(await button.isDisabled(),true);assert.equal(posts,1);
   stale=false;evidence.validation={live_eligible:false,status:'unverified',issues:['Source provenance is unavailable.']};
   await panel.getByRole('button',{name:'Reload AI evidence'}).click();
   await panel.getByText('Evidence: unverified',{exact:true}).waitFor();
   assert.equal(await button.isDisabled(),true);assert.equal(posts,1);
   assert.equal(await panel.getByText('Evidence check expired. Reload before generating a review.',{exact:true}).count(),0);
   assert.deepEqual(errors,[]);
   console.log(`${width}: disabled, mocked review, evidence citations, stale reset and ineligible evidence passed`);
   await p.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
