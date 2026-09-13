const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 fs.mkdirSync('futures-audit',{recursive:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto('http://localhost:8501/?page=spx_nq_futures');
  if(process.env.SCANNER_REFRESH_LIVE==='1') {
   await page.getByText('Refresh live bars',{exact:true}).click();
   assert.equal(await page.getByRole('checkbox',{name:'Refresh live bars',exact:true}).isChecked(),true);
  }
  await page.getByRole('button',{name:'Load Context',exact:true}).click();
  await page.getByRole('tab',{name:'Decision Board',exact:true}).waitFor({timeout:120000});
  for(const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
   for(const name of ['Decision Board','Levels & Scenarios','Cross-Market','Data & Notes']) {
    await page.getByRole('tab',{name,exact:true}).click();
    await page.waitForTimeout(2000);
    assert.equal(await page.locator('[data-testid="stException"]').count(),0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:`futures-audit/${width}-${name.replaceAll(' ','_')}.png`,fullPage:true});
    console.log(`${width}: ${name} passed`);
   }
  }
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
