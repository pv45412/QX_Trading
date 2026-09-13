import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceContext,workspaceHref,workspaceContextItems,updateWorkspaceContext} from './workspace-context.js';
import {workspaceRoutes,workspaceHomes,routeAliases,resolveWorkspaceRoute} from './workspace-routes.js';

test('workspace links preserve validated cross-app context',()=>{
 const context={universe:'sp500',sector:'Information Technology',symbol:'MSFT',etf:'XLK',as_of:'2026-09-10',period:'2y',snapshot:'92'};
 for(const page of ['relative_strength','ticker_history','command_center']){
  const url=new URL(workspaceHref(page,context));assert.deepEqual(workspaceContext(url.search),context);
 }
});

test('canonical destinations and aliases have exactly one active workspace and view',()=>{
 assert.equal(new Set(workspaceRoutes.map(route=>route.page)).size,workspaceRoutes.length);
 assert.deepEqual(workspaceHomes.map(route=>route.workspace),['Today','Markets','Scanner','Research','Journal','System']);
 for(const page of [...workspaceRoutes.map(route=>route.page),...Object.keys(routeAliases)]){
  const route=resolveWorkspaceRoute(page);
  assert.equal(workspaceHomes.filter(home=>home.workspace===route.workspace).length,1);
  assert.equal(workspaceRoutes.filter(item=>item.page===route.page).length,1);
  const query=new URL(workspaceHref(page,{symbol:'MSFT',universe:'sp500',snapshot:'92'})).searchParams;
  assert.equal(query.get('page'),route.page==='relative_strength'?null:route.page);
  if(route.job_view)assert.equal(query.get('job_view'),route.job_view);
  if(route.history_view)assert.equal(query.get('history_view'),route.history_view);
 }
 assert.equal(resolveWorkspaceRoute(' /scanner/ ').page,'scan');
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
 assert.deepEqual(workspaceContextItems({symbol:'MSFT',etf:'XLK',snapshot:'92'}),
  [['Ticker','MSFT'],['ETF','XLK'],['Report snapshot','92']]);
});
test('navigation cannot propagate invalid values or secrets',()=>{
 assert.deepEqual(workspaceContext('?symbol=<script>&as_of=2026-02-30&period=1000y&snapshot=0&api_key=secret&universe=wrong'),{});
 assert.equal(new URL(workspaceHref('scan',{as_of:'2026-09-10',symbol:'AAPL'},{as_of:''})).searchParams.has('as_of'),false);
 assert.deepEqual(workspaceContext('?symbol=brk.b&etf=xle'),{symbol:'BRK.B',etf:'XLE'});
 assert.equal(new URL(workspaceHref('scan',{symbol:undefined,etf:null,snapshot:92})).searchParams.has('symbol'),false);
});
