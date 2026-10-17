const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');

const baseUrl=process.env.QX_WEB_URL||'http://127.0.0.1:5174';
const outputDir=path.resolve(__dirname,'../../data/reports/full_page_activation');
const routes=[
 ['today-day','?page=today&horizon=DAY&timeframe=5m'],
 ['today-swing','?page=today&horizon=SWING&timeframe=1h'],
 ['today-invest','?page=today&horizon=INVEST&timeframe=1d'],
 ['opportunities','?page=opportunities&horizon=DAY&timeframe=5m'],
 ['opportunities-swing','?page=opportunities&horizon=SWING&timeframe=1h'],
 ['opportunities-invest','?page=opportunities&horizon=INVEST&timeframe=1d'],
 ['trade-day','?page=trade&symbol=SOXL&horizon=DAY&timeframe=5m'],
 ['trade-swing','?page=trade&symbol=SOXL&horizon=SWING&timeframe=1h'],
 ['trade-invest','?page=trade&symbol=SOXL&horizon=INVEST&timeframe=1d'],
 ['portfolio','?page=portfolio'],
 ['research-symbol','?page=research&symbol=SPY&research_mode=symbol'],
 ['research-etf','?page=research&etf=XLK&research_mode=etf_sector'],
 ['research-rs','?page=research&etf=XLK&research_mode=relative_strength'],
 ['research-options','?page=research&symbol=SPY&research_mode=options_strategy'],
 ['research-historical','?page=research&symbol=SPY&research_mode=historical'],
 ['research-long-term','?page=research&symbol=SPY&research_mode=long_term'],
 ['system-overview','?page=system'],
 ['system-providers','?page=schwab'],
 ['system-data','?page=data_cache'],
 ['system-jobs','?page=jobs'],
 ['system-runs','?page=run_history'],
 ['system-rules','?page=strategy_rules'],
];

function compact(value){return String(value||'').replace(/\s+/g,' ').trim();}

(async()=>{
 fs.mkdirSync(path.join(outputDir,'screenshots'),{recursive:true});
 const browser=await chromium.launch({headless:true});
 const results=[];
 try{
  for(const [viewport,width,height] of [['desktop',1920,1080],['mobile',390,844]]){
   for(const [name,query] of routes){
    const page=await browser.newPage({viewport:{width,height}});
    const pageErrors=[];const consoleErrors=[];const failedApi=[];
    page.on('pageerror',error=>pageErrors.push(error.message));
    page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
    page.on('response',response=>{if(response.url().includes('/api/')&&response.status()>=400)failedApi.push({url:response.url(),status:response.status()});});
    const started=Date.now();
    let navigationError='';
    try{
     await page.goto(`${baseUrl}/${query}`,{waitUntil:'domcontentloaded',timeout:30000});
     await page.locator('body').waitFor({state:'visible',timeout:30000});
     await page.waitForTimeout(750);
     const settleTimeout=/^(today|trade)/.test(name)?45000:7000;
     await page.waitForFunction(()=>{
      const loadingText=[...document.querySelectorAll('[role="status"]')].some(element=>/\bloading\b/i.test(element.textContent||''));
      return !document.querySelector('.spin')&&!loadingText;
     },undefined,{timeout:settleTimeout}).catch(()=>{});
     await page.waitForTimeout(250);
    }catch(error){navigationError=error.message;}
    const inventory=await page.evaluate(()=>{
     const visible=element=>{
      const style=getComputedStyle(element);const box=element.getBoundingClientRect();
      return style.visibility!=='hidden'&&style.display!=='none'&&box.width>0&&box.height>0;
     };
     const text=element=>(element?.textContent||'').replace(/\s+/g,' ').trim();
     const pairs=[...document.querySelectorAll('dl > div')].filter(visible).map(row=>({
      label:text(row.querySelector('dt')),value:text(row.querySelector('dd')),
     }));
     const metrics=[...document.querySelectorAll('.qx-portfolio-metric,.qx-system-metric,.qx-risk-grid > div')]
      .filter(visible).map(row=>({label:text(row.querySelector('span')),value:text(row.querySelector('strong'))}));
     const fieldRows=[...document.querySelectorAll('dl > div,.qx-portfolio-metric,.qx-system-metric,.qx-risk-grid > div,.qx-opportunity-fact,.qx-hero-fact,.qx-research-metrics > div')]
      .filter(visible).map(row=>{
       const evidence=row.closest('[data-evidence-region]');
       return {
        label:text(row.querySelector('dt,span')),
        value:text(row.querySelector('dd,strong')),
        source:evidence?.dataset.evidenceSource||'',
        asOf:evidence?.dataset.evidenceAsOf||'',
        freshness:evidence?.dataset.evidenceFreshness||'',
       };
      });
     const controls=[...document.querySelectorAll('button,a[href],input,select,textarea')].filter(visible).map(element=>{
      const formControl=['INPUT','SELECT','TEXTAREA'].includes(element.tagName);
      const associatedLabels=[...(element.labels||[])].map(text).join(' ');
      return {
       tag:element.tagName.toLowerCase(),
       name:element.getAttribute('aria-label')||associatedLabels||element.getAttribute('title')||element.getAttribute('placeholder')||(formControl?'':text(element))||'',
       value:formControl?element.value:null,
      };
     });
     const boxes=[...document.querySelectorAll('article,section')].filter(visible).map(element=>({
      heading:text(element.querySelector('h1,h2,h3')),textLength:text(element).length,
     }));
     const statusWords=['AVAILABLE','UNAVAILABLE','BLOCKED','PARTIAL','STALE','FRESH','DEGRADED','ERROR','RESEARCH_ONLY'];
     const body=text(document.body).toUpperCase();
     return {
      title:document.title,
      headings:[...document.querySelectorAll('h1,h2,h3')].filter(visible).map(text),
      pairs,metrics,fieldRows,controls,boxes,
      statuses:Object.fromEntries(statusWords.map(word=>[word,(body.match(new RegExp(`\\b${word}\\b`,'g'))||[]).length])),
      overflow:document.documentElement.scrollWidth>window.innerWidth,
     };
    });
    const emptyPairs=[...inventory.pairs,...inventory.metrics].filter(item=>!compact(item.label)||!compact(item.value));
    const unnamedControls=inventory.controls.filter(control=>!compact(control.name));
    const emptyBoxes=inventory.boxes.filter(box=>box.textLength===0);
    const missingFieldEvidence=inventory.fieldRows.filter(field=>!compact(field.source)||!compact(field.freshness));
    const currentWithoutAsOf=inventory.fieldRows.filter(field=>/CURRENT|FRESH|POINT_IN_TIME/i.test(field.freshness)
      && (!compact(field.asOf)||field.asOf==='UNAVAILABLE'));
    const invalidTitle=!inventory.title.startsWith('QX Platform | ');
    const screenshot=path.join(outputDir,'screenshots',`${name}-${viewport}.png`);
    await page.screenshot({path:screenshot,fullPage:true});
    results.push({name,viewport,url:page.url(),durationMs:Date.now()-started,navigationError,pageErrors,consoleErrors,failedApi,
     emptyPairs,unnamedControls,emptyBoxes,missingFieldEvidence,currentWithoutAsOf,invalidTitle,...inventory});
    console.log(`${viewport} ${name} ${Date.now()-started}ms`);
    await page.close();
   }
  }
 }finally{await browser.close();}
 fs.writeFileSync(path.join(outputDir,'live-value-audit.json'),JSON.stringify(results,null,2));
 const failures=results.filter(result=>result.navigationError||result.pageErrors.length||result.consoleErrors.length||result.failedApi.length||
  result.overflow||result.emptyPairs.length||result.unnamedControls.length||result.emptyBoxes.length||result.missingFieldEvidence.length||
  result.currentWithoutAsOf.length||result.invalidTitle);
 const summary={routes:results.length,failures:failures.map(result=>({name:result.name,viewport:result.viewport,navigationError:result.navigationError,
  pageErrors:result.pageErrors,consoleErrors:result.consoleErrors,failedApi:result.failedApi,overflow:result.overflow,
  emptyPairs:result.emptyPairs,unnamedControls:result.unnamedControls,emptyBoxes:result.emptyBoxes,
  missingFieldEvidence:result.missingFieldEvidence,currentWithoutAsOf:result.currentWithoutAsOf,invalidTitle:result.invalidTitle}))};
 fs.writeFileSync(path.join(outputDir,'live-value-audit-summary.json'),JSON.stringify(summary,null,2));
 console.log(JSON.stringify(summary,null,2));
 if(failures.length)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
