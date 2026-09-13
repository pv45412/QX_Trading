import React,{useEffect,useRef,useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {formatTimestampET} from './data-utils';

export default function SchwabMovers(){
 const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const pending=useRef(null);
 useEffect(()=>()=>pending.current?.abort(),[]);
 async function refresh(){
  if(pending.current)return;
  const controller=new AbortController();pending.current=controller;
  setBusy(true);setError('');
  const timeout=setTimeout(()=>controller.abort(),70000);
  try{
   const response=await fetch('/api/schwab/movers',{method:'POST',headers:{'x-qx-refresh':'1'},signal:controller.signal});
   if(!response.ok)throw Error('Schwab movers unavailable. No fallback used.');
   setData(await response.json());
  }catch(e){setError(e.name==='AbortError'?'Request interrupted or timed out.':e.message);}
  finally{clearTimeout(timeout);pending.current=null;setBusy(false);}
 }
 return <section className="market-movers" aria-label="Schwab ranked movers">
  <div className="section-head"><div><h2>Schwab Top Movers · S&P 500</h2><p>Broker-ranked subsets · separate from the universe and sector filters</p></div><button onClick={refresh} disabled={busy} aria-label="Fetch Schwab top movers" title="Fetch Schwab top movers"><RefreshCw size={15} className={busy?'spin':''}/></button></div>
  {error&&<p role="alert">{error}{data?' Previous results retained.':''}</p>}
  {!data?<p role="status">{busy?'Requesting Schwab movers...':'Not requested'}</p>:<>
   <p className="coverage-note">Retrieved {formatTimestampET(data.retrieved_at)} · market timestamp unavailable · freshness unverified · not full-index breadth</p>
   <div className="mover-columns">{[['highest','Highest changes'],['lowest','Lowest changes']].map(([key,title])=><div key={key}><h3>{title}</h3><div className="table-scroll"><table><thead><tr><th>Stock</th><th>Last</th><th>Change</th></tr></thead><tbody>{(data.groups?.[key] || []).map(r=><tr key={r.symbol}><td>{r.symbol}</td><td>{(Number(r.last) || 0).toFixed(2)}</td><td className={r.return<0?'negative':'positive'}>{(Number(r.return || 0)*100).toFixed(2)}%</td></tr>)}</tbody></table></div>{!(data.groups?.[key] || []).length&&<p>No ranked results returned.</p>}</div>)}</div>
  </>}
 </section>;
}
