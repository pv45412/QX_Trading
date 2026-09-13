const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

// Read-only UI checks. A live Schwab diagnostic needs explicit invocation.
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 fs.mkdirSync('evidence-audit',{recursive:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  async function settled(){
   await page.waitForFunction(()=>!document.querySelector('[data-testid="stApp"][data-test-script-state="running"]'),{},{timeout:90000});
   assert.equal(await page.locator('[data-testid="stException"]').count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  }
  await page.goto('http://localhost:8501/?page=spx_nq_futures');
  await page.getByText('Contract & quote checks',{exact:true}).click();
  const check=page.getByRole('button',{name:'Check Schwab ES / NQ',exact:true});
  await check.waitFor();
  await settled();
  assert.equal(await page.getByText(/Schwab check:/).count(),0);
  if(process.env.SCANNER_CHECK_LIVE==='1'){
   await check.click();
   await page.getByText(/Schwab check:/).waitFor({timeout:90000});
   await settled();
   assert.match(await page.locator('[data-testid="stMain"]').innerText(),/not continuously monitored/);
   assert.match(await page.locator('[data-testid="stMain"]').innerText(),/No synchronized cash-close comparison or live signal/);
  }
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});
   await settled();
   await page.screenshot({path:`evidence-audit/futures-${width}.png`,fullPage:true});
   console.log(`Futures controls ${width}: passed`);
  }
  await page.goto('http://localhost:8501/?page=spx_nq_futures&as_of=2026-09-10');
  await page.getByText(/No point-in-time futures snapshot is loaded/).waitFor();
  assert.equal(await page.getByRole('button',{name:'Check Schwab ES / NQ',exact:true}).count(),0);
  await settled();
  console.log('Historical futures: current quote action withheld');
  await page.goto('http://localhost:8501/?page=journal&symbol=MSFT');
  await page.getByRole('combobox',{name:'Record type',exact:true}).click();
  await page.getByRole('option',{name:'Live (user-reported)',exact:true}).click();
  const payload=page.getByRole('textbox',{name:'Normalized execution JSON',exact:true});
  await payload.waitFor();
  assert.equal(await page.getByRole('textbox',{name:'Symbol',exact:true}).inputValue(),'MSFT');
  await page.getByRole('button',{name:'Download import schema',exact:true}).waitFor();
  await payload.fill('{}');
  await page.getByRole('button',{name:'Preview comparison',exact:true}).click();
  await settled();
  assert.match(await page.locator('[data-testid="stMain"]').innerText(),/Live broker sync: disabled/);
  await page.getByText(/Import fields must exactly match the normalized schema/).waitFor();
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});
   await settled();
   await page.screenshot({path:`evidence-audit/journal-${width}.png`,fullPage:true});
   console.log(`Journal preview controls ${width}: passed`);
  }
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
