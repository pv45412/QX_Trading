import React, {useMemo, useState} from 'react';
import {Target, Shield, Zap, ArrowDownUp, Info, Search, Download, Compass, BarChart3, TrendingUp, TrendingDown} from 'lucide-react';
import {csvCell} from './data-utils';

const percent = n => Number.isFinite(n) ? `${n >= 0 ? '+' : ''}${(n*100).toFixed(2)}%` : '—';
const tone = n => Number.isFinite(n) ? n > 0 ? 'positive' : n < 0 ? 'negative' : '' : 'muted';
const columns = [
 ['Ticker','etf','Sector ETF and sector name.'],
 ['RS rank','rs_rank','1–99 cross-sectional rank of 21-session ETF/SPY ratio change. Ties share midpoint rank. Requires full universe coverage.'],
 ['MTD','mtd','Closing-price return from the last available close of the previous calendar month.'],
 ['RS days (21)','rs_days','Number of the last 21 sessions when ETF close-to-close return exceeded SPY return.'],
 ['Up / Down','up_down','Percentage of SPY-negative sessions when the ETF closed higher, over 21 sessions.'],
 ['Corr vs QQQ','corr_qqq','Pearson correlation of 21 daily ETF returns with QQQ.'],
 ['Corr vs DIA','corr_dia','Pearson correlation of 21 daily ETF returns with DIA.'],
 ['Corr. Δ vs SPY','correction_excess','ETF return minus SPY return during SPY’s largest peak-to-trough drawdown in the cached window.'],
 ['RS line 21D','rs_change','Change in ETF close / SPY close over 21 sessions.'],
 ['RS line','days_off_high','Sessions since the most recent highest ratio in the last 22 closes. Zero means at the 21-session high.'],
];

export default function ReferenceRanking({onSelect, data, error, busy, onRetry, symbol}) {
 const [sort,setSort]=useState({key:'rs_change',asc:false}),[query,setQuery]=useState('');
 const [activeTab, setActiveTab] = useState('matrix'); // 'matrix' | 'table' | 'heatmap'

 const rows=useMemo(()=>(data?.rows||[]).filter(r=>`${r.etf} ${r.sector}`.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>{
  const x=a[sort.key],y=b[sort.key];if(x==null)return y==null?0:1;if(y==null)return -1;
  return (sort.asc?1:-1)*(typeof x==='number'?x-y:String(x).localeCompare(String(y)));
 }),[data,query,sort]);

 const available=(data?.rows||[]).filter(r=>r.status==='CACHED_UNVERIFIED');

 // Compute Sector Rotation Quadrants
 const quadrants = useMemo(() => {
  const result = { leading: [], weakening: [], lagging: [], improving: [] };
  available.forEach(r => {
   const rs = r.rs_change || 0;
   const days = r.days_off_high ?? 21;
   if (rs >= 0 && days <= 5) result.leading.push(r);
   else if (rs >= 0 && days > 5) result.weakening.push(r);
   else if (rs < 0 && days > 10) result.lagging.push(r);
   else result.improving.push(r);
  });
  return result;
 }, [available]);

 const panels=[
  ['NEW RS LINE HIGHS','At 21-session RS line high',Target,available.filter(r=>r.days_off_high===0).sort((a,b)=>b.rs_change-a.rs_change).slice(0,6),()=> '21D high'],
  ['CORRECTION LEADERS',available[0]?.correction?`Δ vs SPY · ${available[0].correction.start.slice(0,10)} → ${available[0].correction.end.slice(0,10)}`:'Excess return during SPY drawdown',Shield,available.filter(r=>r.correction_excess!=null).sort((a,b)=>b.correction_excess-a.correction_excess).slice(0,3),r=>percent(r.correction_excess)],
  ['UP ON DOWN DAYS','ETF positive when SPY closed lower · 21D',Zap,available.filter(r=>r.up_down!=null).sort((a,b)=>b.up_down-a.up_down).slice(0,3),r=>`${Math.round(r.up_down*100)}%`],
 ];

 function download() {
  const keys=['etf','sector',...columns.slice(1).map(c=>c[1]),'as_of','source'];
  const csv=[keys.join(','),...rows.map(row=>keys.map(key=>csvCell(row[key])).join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const a=document.createElement('a');
  a.href=url;a.download='qx-rs-analytics-fractional-units.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }

 function value(r,key) {
  const n=r[key];if(n==null)return <span className="muted">—</span>;
  if(key==='rs_rank')return <span className="rank-value">{n}<meter min="1" max="99" value={n} aria-label={`${r.etf} RS rank`}/></span>;
  if(key==='rs_days')return <>{n}<small className="inline-note">/21 ({Math.round(n/21*100)}%)</small></>;
  if(key==='up_down')return <>{Math.round(n*100)}% <small className="inline-note">({r.up_days}/{r.down_days})</small></>;
  if(key.startsWith('corr_'))return n.toFixed(2);
  if(key==='days_off_high')return n===0?<span className="positive">21D high</span>:<span className="muted">{n}d off high</span>;
  return percent(n);
 }

 return <>
 {error&&<div className="error reload-error" role="alert"><span>{error} {data?'Showing the last successfully loaded results.':'No analytics loaded.'}</span><button onClick={onRetry} disabled={busy}>Retry</button></div>}
 <div className="analytics-status" role="status">{busy?'Loading cached analytics…':data?`${data.coverage}/${data.universe} ETFs have aligned cached history · freshness unverified`:'Analytics unavailable'}{available.length>0&&<span>Through {available[0].as_of.slice(0,10)}</span>}</div>
 
 <section className="summary-grid reference-summaries">{panels.map(([title,subtitle,Icon,items,format])=><article key={title}><h2><Icon size={14}/>{title}</h2><p>{subtitle}</p>{items.map(r=><button className="summary-row" key={r.etf} onClick={()=>onSelect(r.etf)}><span><b>{r.etf}</b><small>{r.sector}</small></span><span className={title==='CORRECTION LEADERS'?tone(r.correction_excess):'positive'}>{format(r)}</span></button>)}{!items.length&&<p className="panel-empty">{data?'No qualifying results in available history':busy?'Loading…':'Unavailable'}</p>}</article>)}</section>

 <section className="reference-ranking" id="ranking">
  <div className="section-head">
   <div>
    <h2>Sector Relative Strength & Rotation Studio</h2>
    <p>Cross-sectional RS Ranking, Sector Rotation Quadrants & Institutional Down-Market Defense</p>
   </div>
   <div className="tools">
    <div className="qx-view-toggle">
     <button className={activeTab === 'matrix' ? 'active' : ''} onClick={() => setActiveTab('matrix')}><Compass size={13}/> Quadrant Matrix</button>
     <button className={activeTab === 'table' ? 'active' : ''} onClick={() => setActiveTab('table')}><BarChart3 size={13}/> Ranking Table</button>
     <button className={activeTab === 'heatmap' ? 'active' : ''} onClick={() => setActiveTab('heatmap')}><Zap size={13}/> Performance Heatmap</button>
    </div>
    <label><Search size={14}/><input aria-label="Search analytics sectors" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Find sector"/></label>
    <button onClick={download} disabled={!rows.length} title="Export analytics (fractional units)" aria-label="Export analytics"><Download size={14}/></button>
   </div>
  </div>

  {/* 4-QUADRANT SECTOR ROTATION MATRIX */}
  {activeTab === 'matrix' && (
   <div className="qx-rotation-matrix-container">
    <div className="qx-matrix-header">
     <h3>Institutional Sector Rotation Matrix (RRG Style)</h3>
     <p>Sectors classified by 21D Relative Momentum (X-axis) and RS High Recency (Y-axis)</p>
    </div>
    <div className="qx-matrix-grid">
     <div className="qx-quadrant qx-quad-leading">
      <div className="qx-quad-head">
       <span className="qx-quad-badge leading"><TrendingUp size={14}/> LEADING</span>
       <small>Strong RS + At/Near 21D Highs</small>
      </div>
      <div className="qx-quad-chips">
       {quadrants.leading.map(r => (
        <button key={r.etf} onClick={() => onSelect(r.etf)} className={`qx-chip ${symbol === r.etf ? 'active' : ''}`}>
         <strong>{r.etf}</strong>
         <span>{percent(r.rs_change)}</span>
        </button>
       ))}
       {!quadrants.leading.length && <p className="muted">No sectors currently leading</p>}
      </div>
     </div>

     <div className="qx-quadrant qx-quad-weakening">
      <div className="qx-quad-head">
       <span className="qx-quad-badge weakening"><TrendingDown size={14}/> WEAKENING</span>
       <small>Positive 21D RS + Pulling Off Highs</small>
      </div>
      <div className="qx-quad-chips">
       {quadrants.weakening.map(r => (
        <button key={r.etf} onClick={() => onSelect(r.etf)} className={`qx-chip ${symbol === r.etf ? 'active' : ''}`}>
         <strong>{r.etf}</strong>
         <span>{percent(r.rs_change)}</span>
        </button>
       ))}
       {!quadrants.weakening.length && <p className="muted">No sectors in weakening phase</p>}
      </div>
     </div>

     <div className="qx-quadrant qx-quad-improving">
      <div className="qx-quad-head">
       <span className="qx-quad-badge improving"><TrendingUp size={14}/> IMPROVING</span>
       <small>Negative RS + Turning Up Off Lows</small>
      </div>
      <div className="qx-quad-chips">
       {quadrants.improving.map(r => (
        <button key={r.etf} onClick={() => onSelect(r.etf)} className={`qx-chip ${symbol === r.etf ? 'active' : ''}`}>
         <strong>{r.etf}</strong>
         <span>{percent(r.rs_change)}</span>
        </button>
       ))}
       {!quadrants.improving.length && <p className="muted">No sectors in improving phase</p>}
      </div>
     </div>

     <div className="qx-quadrant qx-quad-lagging">
      <div className="qx-quad-head">
       <span className="qx-quad-badge lagging"><TrendingDown size={14}/> LAGGING</span>
       <small>Negative RS + Deep Off Highs</small>
      </div>
      <div className="qx-quad-chips">
       {quadrants.lagging.map(r => (
        <button key={r.etf} onClick={() => onSelect(r.etf)} className={`qx-chip ${symbol === r.etf ? 'active' : ''}`}>
         <strong>{r.etf}</strong>
         <span>{percent(r.rs_change)}</span>
        </button>
       ))}
       {!quadrants.lagging.length && <p className="muted">No lagging sectors</p>}
      </div>
     </div>
    </div>
   </div>
  )}

  {/* SECTOR PERFORMANCE HEATMAP */}
  {activeTab === 'heatmap' && (
   <div className="qx-heatmap-container">
    <h3>21-Session Relative Strength Heatmap</h3>
    <div className="qx-heatmap-grid">
     {rows.map(r => {
      const val = r.rs_change || 0;
      const bg = val > 0.03 ? 'rgba(0, 230, 118, 0.25)' : val > 0 ? 'rgba(0, 230, 118, 0.12)' : val < -0.03 ? 'rgba(255, 23, 68, 0.25)' : 'rgba(255, 23, 68, 0.12)';
      const border = val > 0 ? '#00e676' : '#ff1744';
      return (
       <div key={r.etf} className="qx-heatmap-cell" style={{ background: bg, borderColor: border }} onClick={() => onSelect(r.etf)}>
        <div className="qx-hm-symbol">{r.etf}</div>
        <div className="qx-hm-sector">{r.sector}</div>
        <div className={`qx-hm-value ${tone(val)}`}>{percent(val)}</div>
        <div className="qx-hm-sub">Rank #{r.rs_rank}</div>
       </div>
      );
     })}
    </div>
   </div>
  )}

  {/* RANKING TABLE */}
  {(activeTab === 'table' || activeTab === 'matrix') && (
   <div className="table-scroll">
    <table>
     <thead>
      <tr>
       {columns.map(([label,key,help])=><th key={key} aria-sort={sort.key===key?(sort.asc?'ascending':'descending'):'none'}><button onClick={()=>setSort(s=>({key,asc:s.key===key?!s.asc:false}))}>{label}<ArrowDownUp size={10}/></button><span className="metric-help" tabIndex="0" aria-label={help}><Info size={10}/><span role="tooltip">{help}</span></span></th>)}
      </tr>
     </thead>
     <tbody>
      {rows.map(r=><tr key={r.etf} onClick={()=>onSelect(r.etf)} className={symbol===r.etf?'selected':''}><td><button className="ticker" onClick={()=>onSelect(r.etf)} aria-pressed={symbol===r.etf}><b>{r.etf}</b><small>{r.sector}</small></button></td>{columns.slice(1).map(([,key])=><td key={key} className={['mtd','rs_change','correction_excess','corr_qqq','corr_dia'].includes(key)?tone(r[key]):''}>{value(r,key)}</td>)}</tr>)}
     </tbody>
    </table>
   </div>
  )}

  {data&&!rows.length&&<div className="empty">No sectors match “{query}”. <button onClick={()=>setQuery('')}>Clear search</button></div>}
  
  <div className="qx-strategy-guide-box">
   <h4><Info size={15}/> How Traders Use Sector Rotation Data</h4>
   <ul>
    <li><strong>Leading Sector Focus:</strong> Look for long stock/option setups only in ETFs in the <em>Leading Quadrant</em> or with <em>21D High RS</em>. Outperforming sectors absorb market pullbacks significantly better.</li>
    <li><strong>Up On Down Days (%):</strong> High percentages (&gt;60%) indicate aggressive institutional accumulation during market drops — prime candidates for trend continuation.</li>
    <li><strong>Correction Excess Return:</strong> Sectors with positive excess returns during SPY drawdowns serve as market-defensive leaders when the index experiences volatile selling.</li>
   </ul>
  </div>

  <p className="coverage-note">{data&&data.coverage<data.universe?'Incomplete cache coverage: rankings and unavailable metrics are withheld. ':''}Closing-price analytics, not total returns. Correction dates are computed from the cached SPY window; they are not copied from the reference.</p>
 </section>
 </>;
}

