import React, {useEffect, useRef, useState, useMemo} from 'react';
import {ExternalLink, RefreshCw, PieChart, TrendingUp, Info} from 'lucide-react';
import {summarizeHoldings, strengthOrder} from './holdings-utils';
import {formatTimestampET} from './data-utils';

export default function Holdings({symbol,onAvailabilityChange}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 const [loading,setLoading]=useState(true),[refreshing,setRefreshing]=useState(false),[refreshError,setRefreshError]=useState('');
 const refreshRequest=useRef(null);
 const [view,setView]=useState('strength');
 
 const validate=payload=>{
  if(payload?.symbol!==symbol||!summarizeHoldings(payload.rows))throw Error('Compatible saved fund holdings are unavailable.');
  return payload;
 };

 useEffect(()=>{const controller=new AbortController();let active=true;
  const timeout=setTimeout(()=>{if(active){active=false;setError('Holdings request timed out. Please retry.');setLoading(false);controller.abort();}},15000);
  setData(null);setError('');setLoading(true);setRefreshing(false);setRefreshError('');
  fetch(`/api/rotation/${encodeURIComponent(symbol)}/holdings`,{signal:controller.signal})
   .then(r=>{if(!r.ok)throw Error(r.status===404?'No saved fund holdings are available.':'Compatible saved fund holdings are unavailable.');return r.json();})
   .then(validate).then(payload=>{if(active)setData(payload);})
   .catch(e=>{if(active&&e.name!=='AbortError')setError(e.message);})
   .finally(()=>{clearTimeout(timeout);if(active)setLoading(false);});
  return ()=>{active=false;clearTimeout(timeout);controller.abort();
   if(refreshRequest.current){clearTimeout(refreshRequest.current.timeout);refreshRequest.current.controller.abort();refreshRequest.current=null;}
  };
 },[symbol,attempt]);

 const currentData=data?.symbol===symbol?data:null;
 useEffect(()=>{
  onAvailabilityChange?.(currentData ? 'SOURCE_BACKED' : error && !loading ? 'UNAVAILABLE' : 'LOADING');
 },[currentData,error,loading,onAvailabilityChange]);
 
 const refresh=async()=>{
  if(refreshRequest.current||loading)return;
  const request={controller:new AbortController()};refreshRequest.current=request;
  const active=()=>refreshRequest.current===request&&!request.controller.signal.aborted;
  const retained=currentData?'Previously loaded holdings are unchanged.':'No holdings loaded.';
  setRefreshing(true);setRefreshError('');
  request.timeout=setTimeout(()=>{if(active()){
   setRefreshError(`Holdings refresh timed out. ${retained}`);setRefreshing(false);
   request.controller.abort();refreshRequest.current=null;
  }},15000);
  try{
   const response=await fetch(`/api/rotation/${encodeURIComponent(symbol)}/holdings/refresh`,{
    method:'POST',headers:{'X-Scanner-Refresh':'1'},signal:request.controller.signal});
   if(!response.ok)throw Error('Refresh failed');
   const payload=validate(await response.json());
   if(active()){
    setData(previous=>payload.refresh_error&&previous?.symbol===symbol?previous:payload);
    setError('');setRefreshError(payload.refresh_error||'');
   }
  }catch(e){if(active()&&e.name!=='AbortError')setRefreshError(`Holdings refresh failed. ${retained}`);}
  finally{clearTimeout(request.timeout);if(refreshRequest.current===request){refreshRequest.current=null;setRefreshing(false);}}
 };

 const summary = currentData ? summarizeHoldings(currentData.rows) : null;
 const percentage = value => value == null ? 'Unavailable' : `${(value*100).toFixed(2)}%`;

 // Calculate Top Outperforming Holding
 const topOutperformer = useMemo(() => {
  if (!summary?.ranked) return null;
  const withRS = summary.ranked.filter(r => r.analytics?.rs_change != null);
  if (!withRS.length) return null;
  return withRS.sort((a, b) => b.analytics.rs_change - a.analytics.rs_change)[0];
 }, [summary]);

 return <section className="detail" id="holdings">
  <div className="section-head">
   <div>
    <h2>{symbol} ETF Constituents & Weight Analysis</h2>
    <p>Fund constituents · ETF weight distribution and single-stock RS context · not broker Portfolio positions</p>
   </div>
   <div className="tools">
    <a className="reference-link" href={`https://etfdb.com/etf/${encodeURIComponent(symbol)}/#holdings`} target="_blank" rel="noreferrer">ETFdb reference <ExternalLink size={13}/></a>
    <button type="button" onClick={refresh} disabled={loading||refreshing} aria-label="Refresh fund holdings" title="Refresh fund holdings" aria-busy={refreshing}><RefreshCw size={15} aria-hidden="true" className={refreshing?'spin':''}/></button>
   </div>
  </div>

  <div className="holdings-view" role="group" aria-label="Holdings view">
   <button aria-pressed={view==='strength'} onClick={()=>setView('strength')}>Relative strength</button>
   <button aria-pressed={view==='weights'} onClick={()=>setView('weights')}>Fund weights</button>
  </div>

  {refreshing&&<p role="status">Refreshing fund holdings...</p>}
  {refreshError&&<p className="freshness" role="alert">{refreshError}</p>}
  {error&&<div role="status"><p>{error}</p><button disabled={refreshing} onClick={()=>setAttempt(n=>n+1)}>Retry holdings</button></div>}
  {loading&&<p role="status">Loading saved fund holdings...</p>}

  {currentData&&<>
  {!summary?<p role="status">Holdings data is empty or inconsistent. Concentration cannot be calculated.</p>:<div className="holdings-layout">
  <div>
   {view==='weights'?<div className="table-scroll"><table className="holdings-table"><thead><tr><th>#</th><th>Symbol</th><th>Company</th><th>% Assets</th></tr></thead><tbody>{summary.ranked.map((r,i)=><tr key={r.symbol}><td>{i+1}</td><td><b>{r.symbol}</b></td><td>{r.name || 'Name unavailable'}</td><td><span className="holding-weight"><meter min="0" max="1" value={r.weight} aria-label={`${r.symbol} fund weight`}/>{percentage(r.weight)}</span></td></tr>)}</tbody></table></div>:<div className="table-scroll"><table className="holdings-strength"><thead><tr><th>Holding</th><th>% Assets</th><th title="Change in stock close / SPY close over 21 sessions">RS line 21D</th><th title="Sessions when the stock outperformed SPY">RS days</th><th title="Stock-positive sessions among SPY-negative sessions">Up / Down</th></tr></thead><tbody>{strengthOrder(summary.ranked).map(r=><tr key={r.symbol}><td><b>{r.symbol}</b><small>{r.name}</small></td><td>{percentage(r.weight)}</td><td className={r.analytics?(r.analytics.rs_change>=0?'positive':'negative'):'muted'}>{r.analytics?`${r.analytics.rs_change>=0?'+':''}${percentage(r.analytics.rs_change)}`:'—'}</td><td>{r.analytics?`${r.analytics.rs_days}/21`:'—'}</td><td>{r.analytics?.up_down!=null?`${Math.round(r.analytics.up_down*100)}% (${r.analytics.up_days}/${r.analytics.down_days})`:'—'}</td></tr>)}</tbody></table></div>}
   <p className="coverage-note">Aligned price coverage: {data.analytics_coverage??0}/{summary.ranked.length}. {data.analytics_coverage>0?`Through ${summary.ranked.find(r=>r.analytics)?.analytics.as_of.slice(0,10)} · cached prices, freshness unverified.`:'Date-aligned stock caches unavailable.'}</p>
  </div>

  <aside className="concentration">
   <h3><PieChart size={14}/> Concentration Breakdown</h3>
   <dl>
    <div><dt>Holdings shown</dt><dd>{summary.ranked.length}</dd></div>
    <div><dt>Largest holding</dt><dd>{summary.ranked[0].symbol} <span>{percentage(summary.ranked[0].weight)}</span></dd></div>
    <div><dt>Top 3 concentration</dt><dd>{percentage(summary.topThree)}</dd></div>
    <div><dt>Top 10 total weight</dt><dd>{percentage(summary.total)}</dd></div>
    {topOutperformer && (
     <div>
      <dt><TrendingUp size={12}/> Top RS Outperformer</dt>
      <dd>{topOutperformer.symbol} <span className="positive">+{percentage(topOutperformer.analytics.rs_change)}</span></dd>
     </div>
    )}
   </dl>
   <div className="qx-concentration-meter-box">
    <small>Top 3 Weight Visualizer ({percentage(summary.topThree)})</small>
    <div className="qx-conc-bar-bg">
     <div className="qx-conc-bar-fill" style={{ width: `${Math.min(100, summary.topThree * 100)}%` }}></div>
    </div>
   </div>
   
   <div className="qx-holdings-strategy-note">
    <h4><Info size={12}/> ETF vs Single Stock Strategy</h4>
    <p>Top-three concentration helps explain how single-stock events can influence the ETF. Relative-strength fields provide comparative research context, not a trade recommendation.</p>
   </div>
  </aside>
  </div>}

  <p className="freshness" role="status">{refreshError||currentData.stale_holdings||currentData.holdings_status==='SAVED_UNVERIFIED'?'Saved holdings; freshness unverified. Weights may have changed.':currentData.holdings_status==='REFRESHED_UNSAVED'?'Retrieved holdings; not saved locally.':'Holdings refreshed and saved.'}</p>
  {currentData.cache_warning&&<p role="status">{currentData.cache_warning}</p>}
  <p className="status">{currentData.source} · retrieved {formatTimestampET(currentData.retrieved_at)} · {currentData.holdings_as_of?`holdings effective date ${currentData.holdings_as_of}`:'holdings effective date unavailable'}</p>
  </>}
 </section>;
}
