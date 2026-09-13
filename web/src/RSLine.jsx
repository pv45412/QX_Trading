import React, {useEffect,useState} from 'react';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,Tooltip,CartesianGrid,ReferenceLine} from 'recharts';

export default function RSLine({symbol}) {
 const [result,setResult]=useState(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();let active=true;
  const timeout=setTimeout(()=>{if(active){setError('RS history request timed out. Please retry.');controller.abort();}},15000);
  setResult(null);setError('');
  fetch(`/api/rotation/${encodeURIComponent(symbol)}/line`,{signal:controller.signal})
   .then(r=>{if(!r.ok)throw Error('Date-aligned cached RS history unavailable.');return r.json();})
   .then(data=>{if(active)setResult(data);}).catch(e=>{if(active&&e.name!=='AbortError')setError(e.message);}).finally(()=>clearTimeout(timeout));
  return ()=>{active=false;clearTimeout(timeout);controller.abort();};
 },[symbol,attempt]);
 return <section aria-label={`${symbol} relative-strength history`}>
  <p className="chart-provenance">ETF / SPY closing-price ratio · cached history</p>
  {error?<div className="chart-placeholder"><p role="status">{error}</p><button onClick={()=>setAttempt(n=>n+1)}>Retry chart</button></div>:!result?<div className="chart-placeholder"><p role="status">Loading RS history...</p></div>:<>
   <p className="chart-provenance">Through {result.as_of.slice(0,10)} · ETF source: {result.sector_source} · SPY source: {result.benchmark_source} · freshness unverified</p>
   <div style={{height:340,width:'100%',marginTop:18}}>
    <ResponsiveContainer width="100%" height="100%"><LineChart data={result.points} margin={{top:10,right:20,bottom:10,left:0}}>
     <CartesianGrid stroke="#252e3b" strokeDasharray="2 4"/><XAxis dataKey="date" tickFormatter={v=>v.slice(5,10)} minTickGap={50} stroke="#8894a5" tick={{fontSize:10}}/>
     <YAxis domain={['auto','auto']} tickFormatter={v=>v.toFixed(3)} stroke="#8894a5" width={65}/>
     <Tooltip labelFormatter={v=>String(v).slice(0,10)} formatter={v=>[Number(v).toFixed(4),'RS ratio']} contentStyle={{background:'#191f2b',border:'1px solid #303744'}}/>
     {result.summary?.correction&&<ReferenceLine x={result.summary.correction.start} stroke="#697786" strokeDasharray="3 4"/>}
     {result.summary?.correction&&<ReferenceLine x={result.summary.correction.end} stroke="#697786" strokeDasharray="3 4"/>}
     <Line dataKey="ratio" stroke="#3478ff" strokeWidth={1.8} dot={false} isAnimationActive={false}/>
    </LineChart></ResponsiveContainer>
   </div>
   {result.summary?.correction&&<p className="chart-provenance">Correction window (dashed markers): {result.summary.correction.start.slice(0,10)} to {result.summary.correction.end.slice(0,10)}</p>}
   <dl className="chart-stats">{[['Current RS',result.summary?.current_rs],['21-session high',result.summary?.rs_high],['21D RS change',result.summary?.rs_change],['Sessions',result.points.length]].map(([label,value],i)=><div key={label}><dt>{label}</dt><dd>{value==null?'Unavailable':i===2?`${(value*100).toFixed(2)}%`:i===3?value:value.toFixed(4)}</dd></div>)}</dl>
  </>}
 </section>;
}
