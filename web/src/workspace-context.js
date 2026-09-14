import {resolveWorkspaceRoute} from './workspace-routes.js';

const universes=new Set(['etfs','custom','sp500','sp100','nasdaq_100','dow_jones','russell_2000','scanner_review']);
const periods=new Set(['1mo','3mo','6mo','1y','2y','3y','5y','max']);
const keys=['universe','sector','symbol','etf','period','as_of','snapshot'];
const contextFromValues=values=>workspaceContext(new URLSearchParams(
 Object.entries(values).filter(([,value])=>typeof value==='string')).toString());

export function workspaceContext(search='') {
 const query=new URLSearchParams(search),result={};
 for(const key of keys){
  let value=(query.get(key)||'').trim(),valid=false;
  if(key==='symbol'||key==='etf'){value=value.toUpperCase();valid=/^[A-Z0-9^/][A-Z0-9.^=/\-]{0,19}$/.test(value);}
  else if(key==='universe')valid=universes.has(value);
  else if(key==='period')valid=periods.has(value);
  else if(key==='as_of')valid=/^\d{4}-\d{2}-\d{2}$/.test(value)&&value.slice(0,4)>='1900'&&value.slice(0,4)<='2100'&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
  else if(key==='snapshot')valid=/^[0-9]{1,19}$/.test(value)&&BigInt(value)>0n&&BigInt(value)<9223372036854775808n;
  else valid=value.length>0&&value.length<=80&&/^[\p{L}\p{N} &/().,\-]+$/u.test(value);
  if(valid)result[key]=value;
 }
 return result;
}

export function workspaceHref(page,context={},updates={}) {
 const route=resolveWorkspaceRoute(page);
 if(!route)throw new Error(`Unknown workspace route: ${page}`);
 const values={...context,...updates};
 const query=new URLSearchParams(contextFromValues(values));
 if(route.page!=='relative_strength')query.set('page',route.page);
 const viewKey=route.page==='jobs'?'job_view':route.page==='run_history'?'history_view':null;
 const options=viewKey==='job_view'?['Pipeline','Schedule']:['Scans','Workflows','Snapshots'];
 const view=route[viewKey]||values[viewKey];
 if(viewKey&&options.includes(view))query.set(viewKey,view);
 return `http://127.0.0.1:5174/${query.size?'?'+query:''}`;
}

export function updateWorkspaceContext(updates,{replace=false}={}) {
 const url=new URL(location.href);
 const context={...workspaceContext(url.search),...contextFromValues(updates)};
 for(const key of keys){
  if(updates[key]==='')delete context[key];
  if(context[key])url.searchParams.set(key,context[key]);else url.searchParams.delete(key);
 }
 if(url.href!==location.href){history[replace?'replaceState':'pushState'](history.state,'',url);window.dispatchEvent(new Event('workspacecontextchange'));}
 return context;
}

export function workspaceContextItems(context={}) {
 return [['Universe','universe'],['Ticker','symbol'],['ETF','etf'],['Sector','sector'],
  ['Period','period'],['As of','as_of'],['Report snapshot','snapshot']]
  .filter(([,key])=>context[key]).map(([label,key])=>[label,context[key]]);
}
