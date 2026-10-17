import {resolveWorkspaceRoute} from './workspace-routes.js';

const universes=new Set(['etfs','custom','sp500','sp100','nasdaq_100','dow_jones','russell_2000','scanner_review']);
const periods=new Set(['1mo','3mo','6mo','1y','2y','3y','5y','max']);
const horizons=new Set(['DAY','SWING','INVEST']);
const timeframes=new Set(['1m','5m','15m','30m','1h','4h','1d','1w']);
const researchModes=new Set(['symbol','etf_sector','relative_strength','options_strategy','historical','long_term']);
const keys=['universe','sector','symbol','etf','period','as_of','snapshot','horizon','timeframe','evaluation_timestamp','evaluation_id','account_id','research_mode'];
const contextFromValues=values=>workspaceContext(new URLSearchParams(
 Object.entries(values).filter(([,value])=>typeof value==='string')).toString());

export function workspaceContext(search='') {
 const query=new URLSearchParams(search),result={};
 for(const key of keys){
  let value=(query.get(key)||'').trim(),valid=false;
  if(key==='symbol'||key==='etf'){value=value.toUpperCase();valid=/^[A-Z0-9^/][A-Z0-9.^=/\-]{0,19}$/.test(value);}
  else if(key==='universe')valid=universes.has(value);
  else if(key==='period')valid=periods.has(value);
  else if(key==='horizon'){value=value.toUpperCase();valid=horizons.has(value);}
  else if(key==='timeframe')valid=timeframes.has(value);
  else if(key==='research_mode')valid=researchModes.has(value);
  else if(key==='as_of')valid=/^\d{4}-\d{2}-\d{2}$/.test(value)&&value.slice(0,4)>='1900'&&value.slice(0,4)<='2100'&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
  else if(key==='snapshot')valid=/^[0-9]{1,19}$/.test(value)&&BigInt(value)>0n&&BigInt(value)<9223372036854775808n;
  else if(key==='evaluation_timestamp')valid=value.length<=40&&Number.isFinite(Date.parse(value))&&/[zZ]|[+-]\d{2}:\d{2}$/.test(value);
  else if(key==='evaluation_id')valid=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
  else if(key==='account_id')valid=/^(?:qxacct|acct|account)_[A-Za-z0-9._:-]{6,120}$/.test(value);
  else valid=value.length>0&&value.length<=80&&/^[\p{L}\p{N} &/().,\-]+$/u.test(value);
  if(valid)result[key]=value;
 }
 return result;
}

export function workspaceHref(page,context={},updates={}) {
 const route=resolveWorkspaceRoute(page);
 if(!route)throw new Error(`Unknown workspace route: ${page}`);
 const values={...context,...updates};
 delete values.page;
 const query=new URLSearchParams(contextFromValues(values));
 if(route.page!=='relative_strength')query.set('page',route.page);
 const viewKey=route.page==='jobs'?'job_view':route.page==='run_history'?'history_view':null;
 const options=viewKey==='job_view'?['Pipeline','Schedule']:['Scans','Workflows','Snapshots'];
 const view=route[viewKey]||values[viewKey];
 if(viewKey&&options.includes(view))query.set(viewKey,view);
 const origin=typeof location!=='undefined'&&location.origin?location.origin:'http://127.0.0.1:5174';
 return `${origin}/${query.size?'?'+query:''}`;
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
  ['Horizon','horizon'],['Timeframe','timeframe'],['Evaluation','evaluation_timestamp'],
  ['Period','period'],['As of','as_of'],['Report snapshot','snapshot'],['Account','account_id']]
  .filter(([,key])=>context[key]).map(([label,key])=>[label,context[key]]);
}
