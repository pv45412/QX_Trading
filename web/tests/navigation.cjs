const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const b=await chromium.launch({channel:'msedge',headless:true});
 fs.mkdirSync('navigation-audit',{recursive:true});
 const destinations=[
  ['Today','Today','command_center'],
  ['Scanner','Scanner','scan'],
  ['Research','Research','ticker_history'],
  ['Journal','Journal','idea_tracking'],
  ['System','System','data_cache'],
 ];
 try{for(const width of [1440,390]){
  const p=await b.newPage({viewport:{width,height:1000}});
  const errors=[];
  p.on('pageerror',error=>errors.push(error.message));
  await p.goto('http://127.0.0.1:5173/');
  for(const [label,active,route] of destinations){
  const nav=p.getByRole('navigation',{name:'Workspace pages'});
  await nav.getByRole('link',{name:label,exact:true}).click();
  await p.locator('.qx-page-header').waitFor({timeout:30000});
  await p.waitForFunction(()=>!document.querySelector('[data-testid="stApp"][data-test-script-state="running"]'),{},{timeout:30000});
  assert.equal(new URL(p.url()).searchParams.get('page'),route);
  const workspaceNav=p.getByRole('navigation',{name:'Workspace pages'});
  assert.equal(await workspaceNav.locator('[aria-current="page"]').count(),1);
  assert.equal(await workspaceNav.getByRole('link',{name:active,exact:true}).getAttribute('aria-current'),'page');
  assert.equal(await p.locator('[data-testid="stException"]').count(),0);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await p.screenshot({path:`navigation-audit/${width}-${route}.png`});
  await workspaceNav.getByRole('link',{name:'Markets',exact:true}).click();
  await p.getByRole('heading',{name:'Relative Strength Dashboard'}).waitFor();
  assert.equal(await p.getByRole('navigation',{name:'Workspace pages'}).getByRole('link',{name:'Markets',exact:true}).getAttribute('aria-current'),'page');
  console.log(`${width}: React to ${active} and back passed`);
  }
  assert.deepEqual(errors,[]);
  await p.close();
 }}finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
