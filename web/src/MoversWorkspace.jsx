import React,{useEffect,useState} from 'react';
import MarketMovers from './MarketMovers';
import SchwabMovers from './SchwabMovers';
import LiveRefresh from './LiveRefresh';
import {workspaceContext,workspaceHref,updateWorkspaceContext} from './workspace-context';

export default function MoversWorkspace({data,onSelect,revision}) {
 const supported=new Set(['etfs','sp500','sp100','nasdaq_100','dow_jones']);
 const initial=workspaceContext(location.search);
 const [universe,setUniverse]=useState(initial.universe||'etfs'),[sector,setSector]=useState(initial.sector||'All sectors');
 const [stocks,setStocks]=useState(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0),[selected,setSelected]=useState(null);
 useEffect(()=>{const restore=()=>{const next=workspaceContext(location.search);setUniverse(next.universe||'etfs');setSector(next.sector||'All sectors');setSelected(null);};window.addEventListener('popstate',restore);return()=>window.removeEventListener('popstate',restore);},[]);
 useEffect(()=>{
  setStocks(null);setError('');setSelected(null);
  if(universe==='etfs'||!supported.has(universe))return;
  const controller=new AbortController();let active=true;
  const timeout=setTimeout(()=>{if(active){setError('Request timed out. Retry loading cached movers.');controller.abort();}},15000);
  fetch(`/api/movers/${universe}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Cached index data unavailable.');return r.json();}).then(d=>{if(active)setStocks(d);}).catch(e=>{if(active&&e.name!=='AbortError')setError(e.message);}).finally(()=>clearTimeout(timeout));
  return()=>{active=false;controller.abort();clearTimeout(timeout);};
 },[universe,revision,attempt]);
 const source=universe==='etfs'?data:stocks;
 const sectors=[...new Set((source?.rows||[]).map(r=>r.sector))].sort();
 const rows=(source?.rows||[]).filter(r=>(sector==='All sectors'||r.sector===sector)&&(!initial.as_of||r.as_of?.slice(0,10)===initial.as_of));
 const labels={etfs:'Sector & industry ETFs',sp500:'S&P 500',sp100:'S&P 100',nasdaq_100:'Nasdaq 100',dow_jones:'Dow Jones'};
 return <>
  {universe!=='etfs'&&supported.has(universe)&&!initial.as_of&&<LiveRefresh key={universe} endpoint={`/api/stock-refresh/${universe}`} label="Refresh index prices" onComplete={()=>setAttempt(n=>n+1)}/>}
  <div className="movers-controls">
   <label>Universe <select aria-label="Movers universe" value={universe} onChange={e=>{setUniverse(e.target.value);setSector('All sectors');setSelected(null);updateWorkspaceContext({universe:e.target.value,sector:''});}}>{!supported.has(universe)&&<option value={universe}>{universe} - unavailable</option>}{Object.entries(labels).map(([id,label])=><option value={id} key={id}>{label}</option>)}<option disabled>Russell 1000 - membership unavailable</option><option disabled>Russell 2000 - membership unverified</option></select></label>
   <label>Sector <select aria-label="Movers sector" value={sector} onChange={e=>{setSector(e.target.value);setSelected(null);updateWorkspaceContext({sector:e.target.value==='All sectors'?'':e.target.value});}}><option>All sectors</option>{!sectors.includes(sector)&&sector!=='All sectors'&&<option>{sector}</option>}{sectors.map(s=><option key={s}>{s}</option>)}</select></label>
  </div>
  {!supported.has(universe)?<p role="status">No supported cached movers universe matches this selection.</p>:error?<p role="alert">{error} <button onClick={()=>setAttempt(n=>n+1)}>Retry movers</button></p>:!source?<p role="status">Loading movers...</p>:<>
   {initial.as_of&&<p className="coverage-note">Requested session {initial.as_of}: {rows.length} matching rows. Other sessions are excluded.</p>}
   {stocks&&universe!=='etfs'&&<p className="coverage-note">{stocks.membership_status} · cache file updated {stocks.membership_updated.slice(0,10)}</p>}
   <MarketMovers data={{...source,rows,universe:rows.length}} title="Market Movers" subtitle={`${labels[universe]} · ${sector}`} onSelect={symbol=>{updateWorkspaceContext({symbol});return universe==='etfs'?onSelect(symbol):setSelected(rows.find(r=>r.etf===symbol));}}/>
   {selected&&<div role="status" className="coverage-note"><strong>{selected.etf} · {selected.name}</strong> · {selected.sector} · source {selected.source} · daily return {(selected.return_1d*100).toFixed(2)}% · through {selected.as_of.slice(0,10)} <a href={workspaceHref('ticker_history',workspaceContext(location.search),{symbol:selected.etf})}>Research {selected.etf}</a></div>}
  </>}
 {!initial.as_of&&<SchwabMovers/>}
 </>;
}
