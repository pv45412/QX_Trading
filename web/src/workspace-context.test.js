import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceContext,workspaceHref,workspaceContextItems,updateWorkspaceContext} from './workspace-context.js';
import {workspaceRoutes,workspaceHomes,routeAliases,resolveWorkspaceRoute} from './workspace-routes.js';

test('workspace links preserve validated cross-app context',()=>{
 const context={universe:'sp500',sector:'Information Technology',symbol:'MSFT',etf:'XLK',as_of:'2026-09-10',period:'2y',snapshot:'92',horizon:'SWING',timeframe:'15m',evaluation_timestamp:'2026-09-10T15:30:00Z',evaluation_id:'eval-92',account_id:'account_hash_1'};
 for(const page of ['relative_strength','ticker_history','command_center','trade']){
  const url=new URL(workspaceHref(page,context));assert.deepEqual(workspaceContext(url.search),context);
 }
});

test('canonical destinations and aliases have exactly one active workspace and view',()=>{
 assert.equal(new Set(workspaceRoutes.map(route=>route.page)).size,workspaceRoutes.length);
 assert.deepEqual(workspaceHomes.map(route=>route.workspace),['Today','Opportunities','Trade','Portfolio','Research','System']);
 for(const page of [...workspaceRoutes.map(route=>route.page),...Object.keys(routeAliases)]){
  const route=resolveWorkspaceRoute(page);
  assert.equal(workspaceHomes.filter(home=>home.page===(route.targetPage||route.page)).length,route.targetPage||route.target?1:0);
  assert.equal(workspaceRoutes.filter(item=>item.page===route.page).length,1);
  const query=new URL(workspaceHref(page,{symbol:'MSFT',universe:'sp500',snapshot:'92'})).searchParams;
  assert.equal(query.get('page'),route.page==='relative_strength'?null:route.page);
  if(route.job_view)assert.equal(query.get('job_view'),route.job_view);
  if(route.history_view)assert.equal(query.get('history_view'),route.history_view);
 }
 assert.equal(resolveWorkspaceRoute(' /scanner/ ').page,'scan');
 assert.equal(resolveWorkspaceRoute('trade').surface,'trade');
 assert.equal(resolveWorkspaceRoute('command_center').targetPage,'today');
 assert.equal(resolveWorkspaceRoute('not_a_page'),null);
 assert.equal(resolveWorkspaceRoute('__proto__'),null);
 assert.throws(()=>workspaceHref('not_a_page'),/Unknown workspace route/);
});

test('view selectors stay with their owning destination and aliases retain legacy intent',()=>{
 const context={symbol:'MSFT',job_view:'Schedule',history_view:'Snapshots',secret:'no'};
 assert.equal(new URL(workspaceHref('jobs',context)).searchParams.get('job_view'),'Schedule');
 assert.equal(new URL(workspaceHref('history',context)).searchParams.get('history_view'),'Scans');
 assert.equal(new URL(workspaceHref('pipeline',context)).searchParams.get('job_view'),'Pipeline');
 for(const page of ['relative_strength','ticker_history','scan']){
  const query=new URL(workspaceHref(page,context)).searchParams;
  assert.equal(query.has('job_view'),false);assert.equal(query.has('history_view'),false);
  assert.equal(query.has('secret'),false);
 }
 assert.equal(new URL(workspaceHref('jobs',{job_view:'invalid'})).searchParams.has('job_view'),false);
});

test('context history preserves router state, hash and unrelated query without duplicate entries',()=>{
 const original={location:globalThis.location,history:globalThis.history,window:globalThis.window};
 const calls=[],events=[],state={navigation:'retained'};
 globalThis.location={href:'http://127.0.0.1:5173/?universe=sp500&symbol=MSFT&etf=XLK&as_of=2026-09-10&snapshot=92&keep=1#holdings'};
 globalThis.history={state,pushState(value,_,url){calls.push(['push',value]);location.href=url.href;},
  replaceState(value,_,url){calls.push(['replace',value]);location.href=url.href;}};
 globalThis.window={dispatchEvent:event=>events.push(event.type)};
 try{
  updateWorkspaceContext({etf:'XLK'});assert.equal(calls.length,0);
  updateWorkspaceContext({symbol:undefined,as_of:'not-a-date'});assert.equal(calls.length,0);
  const next=updateWorkspaceContext({etf:'XLE'});
  assert.equal(next.symbol,'MSFT');assert.equal(next.snapshot,'92');
  assert.equal(new URL(location.href).hash,'#holdings');assert.equal(new URL(location.href).searchParams.get('keep'),'1');
  assert.deepEqual(calls,[['push',state]]);
  updateWorkspaceContext({etf:'XLE'});assert.equal(calls.length,1);
  const latest=updateWorkspaceContext({as_of:'',snapshot:''},{replace:true});
  assert.equal(latest.as_of,undefined);assert.equal(latest.snapshot,undefined);
  assert.equal(latest.universe,'sp500');assert.equal(latest.symbol,'MSFT');
  assert.deepEqual(calls,[['push',state],['replace',state]]);
  assert.deepEqual(events,['workspacecontextchange','workspacecontextchange']);
 }finally{
  for(const [key,value] of Object.entries(original)){
   if(value===undefined)delete globalThis[key];else globalThis[key]=value;
  }
 }
});

test('shared context summary distinguishes chart ETF from research ticker and report snapshot',()=>{
 assert.deepEqual(workspaceContextItems({symbol:'MSFT',etf:'XLK',horizon:'DAY',timeframe:'5m',snapshot:'92'}),
  [['Ticker','MSFT'],['ETF','XLK'],['Horizon','DAY'],['Timeframe','5m'],['Report snapshot','92']]);
});
test('canonical privacy-safe account identifiers survive workspace routing',()=>{
 const account_id='qxacct_0123456789abcdef';
 const url=new URL(workspaceHref('portfolio',{account_id}));
 assert.equal(workspaceContext(url.search).account_id,account_id);
});
test('Research mode is validated and preserved only for approved modes',()=>{
 assert.equal(workspaceContext('?research_mode=long_term').research_mode,'long_term');
 assert.equal(workspaceContext('?research_mode=trade').research_mode,undefined);
 assert.equal(new URL(workspaceHref('research',{research_mode:'etf_sector'})).searchParams.get('research_mode'),'etf_sector');
});
test('navigation cannot propagate invalid values or secrets',()=>{
 assert.deepEqual(workspaceContext('?symbol=<script>&as_of=2026-02-30&period=1000y&snapshot=0&api_key=secret&universe=wrong&horizon=SCALP&timeframe=2m&evaluation_timestamp=not-a-date&account_id=<raw>'),{});
 assert.equal(new URL(workspaceHref('scan',{as_of:'2026-09-10',symbol:'AAPL'},{as_of:''})).searchParams.has('as_of'),false);
 assert.deepEqual(workspaceContext('?symbol=brk.b&etf=xle'),{symbol:'BRK.B',etf:'XLE'});
 assert.deepEqual(workspaceContext('?horizon=swing&timeframe=15m&evaluation_timestamp=2026-09-16T14%3A30%3A00Z&evaluation_id=eval-1&account_id=account_hash_1'),{
  horizon:'SWING',timeframe:'15m',evaluation_timestamp:'2026-09-16T14:30:00Z',evaluation_id:'eval-1',account_id:'account_hash_1',
 });
 assert.equal(workspaceContext('?account_id=123456789').account_id,undefined);
 assert.equal(new URL(workspaceHref('scan',{symbol:undefined,etf:null,snapshot:92})).searchParams.has('symbol'),false);
});
