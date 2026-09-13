const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');

// Read-only live audit; run against the local Streamlit server.
const routes=['command_center','daily_workflow','morning_report','scan','broad_watchlist','heatmap','spx_nq_futures','sector_rotation','ticker_history','options_ideas','options_flow','liquidity_map','backtest','strategy_lab','idea_tracking','journal','jobs','run_history','performance','history','workflow_history','command_snapshots','schwab','data_cache','pipeline_control','automation_control','strategy_rules'];
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const results=[];
 const output=path.resolve('workspace-audit');fs.mkdirSync(output,{recursive:true});
 try {
  for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:1000}});
   for(const route of routes){
    const errors=[];const handler=e=>errors.push(e.message);page.on('pageerror',handler);
    try{
     await page.goto(`http://localhost:8501/?page=${route}`);
     await page.locator('.qx-page-header').waitFor({timeout:30000});
     await page.waitForFunction(()=>!document.querySelector('[data-testid="stApp"][data-test-script-state="running"]'),{},{timeout:30000});
     await page.waitForTimeout(500);
     const exceptions=await page.locator('[data-testid="stException"]').allTextContents();
     const tabs=await page.getByRole('tab').allTextContents();
     const tabChecks=[];
     for(let index=0;index<tabs.length;index++) {
      const tab=page.getByRole('tab').nth(index);
      await tab.click();
      await page.waitForFunction(()=>!document.querySelector('[data-testid="stApp"][data-test-script-state="running"]'),{},{timeout:30000});
      const tabExceptions=await page.locator('[data-testid="stException"]').allTextContents();
      const tabOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      exceptions.push(...tabExceptions);
      tabChecks.push({name:tabs[index],exceptions:tabExceptions,overflow:tabOverflow});
      await page.screenshot({path:path.join(output,`${route}-${width}-tab-${index}.png`)});
     }
     const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
     await page.screenshot({path:path.join(output,`${route}-${width}.png`)});
     const theme=await page.evaluate(()=>({background:getComputedStyle(document.querySelector('[data-testid="stAppViewContainer"]')).backgroundColor,ink:getComputedStyle(document.documentElement).getPropertyValue('--qx-ink').trim()}));
     const themeMismatch=theme.background!=='rgb(14, 17, 23)'||theme.ink!=='#e6e9ee';
     const row={route,width,exceptions,errors,overflow,tabs,tabChecks,theme,themeMismatch};results.push(row);console.log(JSON.stringify(row));
    }catch(e){results.push({route,width,error:e.message});console.log(route,width,e.message);}
    page.off('pageerror',handler);
   }
   await page.close();
  }
 }finally{fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));await browser.close();}
 if(results.some(r=>r.error||r.overflow||r.themeMismatch||r.exceptions?.length||r.errors?.length||r.tabChecks?.some(t=>t.overflow)))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
