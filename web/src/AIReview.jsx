import React, {useEffect, useState} from 'react';
import {RefreshCw, Sparkles} from 'lucide-react';

async function readResponse(response) {
 const body=await response.json();
 if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:'AI review unavailable.');
 return body;
}

export default function AIReview({symbol, revision}) {
 const [state,setState]=useState({loading:true}),[reload,setReload]=useState(0);
 const [review,setReview]=useState(null),[pending,setPending]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();let active=true;
  setState({loading:true});setReview(null);setError('');setPending(false);
  Promise.all([
   fetch('/api/ai/status',{signal:controller.signal}).then(readResponse),
   fetch(`/api/ai/evidence/${encodeURIComponent(symbol)}`,{signal:controller.signal}).then(readResponse).then(evidence=>({evidence})).catch(e=>({evidenceError:e.message})),
  ]).then(([status,result])=>{if(active)setState({status,...result,loading:false});})
    .catch(e=>{if(active)setState({loading:false,evidenceError:e.message});});
  return()=>{active=false;controller.abort();};
 },[symbol,revision,reload]);
 useEffect(()=>{
  if(!state.evidence?.validation?.live_eligible)return;
  const id=setTimeout(()=>{setReview(null);setState(s=>({...s,expired:true}));},Math.max(0,Date.parse(state.evidence.expires_at)-Date.now()));
  return()=>clearTimeout(id);
 },[state.evidence]);
 async function generate(){
  if(!available||pending)return;
  const id=state.evidence.snapshot_id;
  setPending(true);setError('');setReview(null);
  try{
   const result=await fetch(`/api/ai/review/${encodeURIComponent(symbol)}`,{method:'POST',headers:{'Content-Type':'application/json','x-qx-ai':'1'},body:JSON.stringify({snapshot_id:id})}).then(readResponse);
   if(result.snapshot_id!==id||Date.parse(result.expires_at)<=Date.now())throw new Error('Review expired or evidence changed. Reload evidence.');
   setReview(result);
  }catch(e){setError(e.message);}finally{setPending(false);}
 }
 const eligible=state.evidence?.schema_version==='qx.rs-review.v2'&&state.evidence?.validation?.live_eligible===true;
 const available=state.status?.enabled&&state.status?.configured&&eligible&&!state.expired&&Date.parse(state.evidence.expires_at)>Date.now();
 return <section id="ai-review" className="ai-review" aria-label="AI evidence review">
  <div className="section-head"><h2><Sparkles size={17}/> AI Evidence Review <span>{symbol}</span></h2><div className="ai-actions">
   <button type="button" aria-label="Reload AI evidence" title="Reload AI evidence" onClick={()=>setReload(n=>n+1)} disabled={state.loading||pending}><RefreshCw size={15}/></button>
   <button type="button" onClick={generate} disabled={!available||pending}>{pending?'Reviewing...':'Generate AI review'}</button>
  </div></div>
  <p role="status">{state.loading?'Checking evidence...':state.status?.message||'AI status unavailable.'}</p>
  {state.evidenceError&&<p className="ai-warning">{state.evidenceError}</p>}
  {state.expired&&<p className="ai-warning">Evidence check expired. Reload before generating a review.</p>}
  {error&&<p role="alert" className="ai-warning">{error}</p>}
  {state.evidence&&<>
   {!eligible&&<div className="ai-warning"><p>Evidence: {state.evidence.validation?.status||'unsupported contract'}</p><ul>{(state.evidence.validation?.issues||['A supported, validated evidence contract is required.']).map(issue=><li key={issue}>{issue}</li>)}</ul></div>}
   <div className="ai-provenance"><span>Daily session: {state.evidence.facts?.bar_date||'Unavailable'}</span><span>Benchmark: SPY</span>
    {Object.entries(state.evidence.facts?.sources || {}).map(([ticker,source])=><span key={ticker}>{ticker}: {source.actual_source}{source.fallback_used?' (fallback)':''}{!source.verified?' (unverified)':''}</span>)}
   </div>
   <p className="ai-disclosure">Generating sends this ETF/SPY evidence snapshot to OpenAI. No account details or credentials are included. API usage may incur charges.</p>
   {review&&<div className="ai-results"><div><h3>Review Priorities</h3><ol>{review.observations?.map(item=><li key={item.id}>{item.text}<small>{item.fields?.map(f=>`facts.${f}`).join(', ')}</small></li>)}</ol></div>
    <div><h3>Checks Before Action</h3><ul>{review.checks?.map(item=><li key={item.id}>{item.text}</li>)}</ul></div></div>}
   <details><summary>Evidence &amp; limitations</summary>
    <ul>{(state.evidence.limitations || []).map(text=><li key={text}>{text}</li>)}</ul>
    <p className="ai-identity">Snapshot: {state.evidence.snapshot_id}</p>
    <pre>{JSON.stringify(state.evidence.facts || {},null,2)}</pre>
   </details>
  </>}
 </section>;
}
