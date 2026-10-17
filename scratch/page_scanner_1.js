

const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const money=v=>v==null?'—':(v<0?'-$':'$')+Math.abs(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const num=(v,d=2)=>v==null||v===''?'—':Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const pctS=v=>v==null?'—':(v>0?'+':'')+(v*100).toFixed(2)+'%';
const pct=v=>v==null?'—':(v*100).toFixed(1)+'%';
const cls=v=>v==null?'':(v>0?'up':v<0?'dn':'');
const bar=(v,max)=>{const p=Math.max(0,Math.min(100,(Math.abs(v)/(max||100))*100));return '<div class="bar"><i style="width:'+p.toFixed(1)+'%;background:'+(v<0?'var(--dn)':'var(--up)')+'"></i></div>'};
async function j(u,opt){const r=await fetch(u,opt);const t=await r.text();if(!r.ok)throw new Error('HTTP '+r.status+' '+(t||'').slice(0,300));try{return JSON.parse(t)}catch(e){throw new Error('bad JSON: '+t.slice(0,200))}}
function kpi(label,value,sub,klass){return '<div class="kpi"><span>'+esc(label)+'</span><b class="'+klass+'">'+value+'</b><em>'+esc(sub||'')+'</em></div>'}
function table(cols,rows,empty){if(!rows||!rows.length)return '<span class="mut">'+esc(empty||'No rows.')+'</span>';
 return '<div class="tablewrap"><table><thead><tr>'+cols.map(c=>'<th'+(c.num?' class="num"':'')+'>'+esc(c.h)+'</th>').join('')+'</tr></thead><tbody>'+
 rows.map(r=>'<tr>'+cols.map(c=>'<td'+(c.num?' class="num"':'')+'>'+c.f(r)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'}
function rsCell(v){ if(v==null) return '<span class="mut">—</span>'; return '<span class="'+cls(v)+'">'+(v>0?'+':'')+num(v,2)+'%</span>' }
function spinner(msg){return '<span class="mut">'+esc(msg||'Loading…')+'</span>'}
// --- exchange-time helpers: the UI shows MARKET time (ET), never UTC ---
const EXCHANGE_TZ='America/New_York';
function exTime(v,withSeconds){
  if(v==null||v==='')return '—';
  const d=new Date(v); if(isNaN(d.getTime()))return '—';
  const o={timeZone:EXCHANGE_TZ,hour12:false,hour:'2-digit',minute:'2-digit'};
  if(withSeconds)o.second='2-digit';
  return d.toLocaleTimeString('en-US',o);
}
function exStamp(v,label){
  if(v==null||v==='')return esc(label||'time unavailable');
  const t=exTime(v,true); if(t==='—')return esc(label||'time unavailable');
  return t+' ET';
}
function exDate(v){
  if(v==null||v==='')return 'undated';
  const d=new Date(v); if(isNaN(d.getTime()))return 'undated';
  return d.toLocaleDateString('en-CA',{timeZone:EXCHANGE_TZ});
}
function exSession(){
  const d=new Date();
  const p=new Intl.DateTimeFormat('en-US',{timeZone:EXCHANGE_TZ,weekday:'short',
    hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d);
  const get=t=>(p.find(x=>x.type===t)||{}).value;
  const wd=get('weekday'), hh=Number(get('hour'))%24, mm=Number(get('minute'));
  if(wd==='Sat'||wd==='Sun')return 'CLOSED_WEEKEND';
  const mins=hh*60+mm;
  if(mins<570)return 'PRE_MARKET';
  if(mins<960)return 'REGULAR';
  if(mins<1200)return 'AFTER_HOURS';
  return 'CLOSED';
}
// Freshness chip. MUST live in HELPERS so every page has it: defining it inside one
// page's script is exactly how the gamma panel once went blank.
function freshChip(f){
  if(!f||!f.overall)return '<span class="mut">—</span>';
  const age=(f.quote||{}).age_seconds;
  const label=f.overall==='FRESH'?(age!=null?num(age,1)+'s':'FRESH'):f.overall;
  const tone=f.overall==='FRESH'?'QUALIFIED_RESEARCH':(f.overall==='UNKNOWN'?'WATCH':'ARMED');
  const why=esc(((f.quote||{}).reason||'')+' | bars '+((f.bars||{}).status||''));
  return '<span class="chip '+tone+'" title="'+why+'">'+esc(label)+'</span>';
}

function setupState(row){
  if(row.error)return 'WATCH';
  const s=row.score; if(s==null)return 'WATCH';
  // Research projection only. Directional score labels are deliberately distinct
  // from execution labels; EXECUTABLE is never produced here.
  if(row.side)return 'QUALIFIED_RESEARCH';
  if(Math.abs(s-70)<=5||Math.abs(s-30)<=5)return 'ARMED';
  return 'WATCH';
}

const CMD_LABEL={'explain-setup':'Explain this setup','what-invalidates':'What would invalidate it?',
 'compare-qualified':'Compare with qualified','update-plan':'Update plan using current data',
 'explain-order-risk':'Explain order risk','review-completed-trade':'Review completed trade'};
const fmtV=v=>v==null?'—':(typeof v==='number'?num(v,2):String(v));
function notesHtml(d){
  const n=d&&d.notes; if(!n)return '<span class="mut">No notes returned.</span>';
  const st=d.staleness||{}, stale=!!(st.staleness&&st.staleness.is_stale);
  let h='<div class="row" style="justify-content:space-between;margin-bottom:6px">'
   +'<div><span class="chip '+(stale?'WATCH':'FRESH')+'">'+(stale?'STALE':'FRESH')+'</span> '
   +'<span class="mut">'+esc(n.notes_version)+' · digest '+esc(n.evidence_digest)+' · scoring '+esc((n.rule_versions||{}).scoring||'')+'</span></div>'
   +'<div class="mut">'+exStamp(n.generated_at)+'</div></div>';
  if(stale){h+='<div class="banner">Previous review marked STALE — '+esc(st.staleness.reason)+'</div>'}
  h+=(n.sections||[]).map(s=>'<details '+(s.number<=2?'open':'')+' style="border-bottom:1px solid var(--line);padding:5px 0">'
    +'<summary style="cursor:pointer"><b>'+s.number+'. '+esc(s.title)+'</b></summary>'
    +'<ul style="margin:6px 0 2px 18px;padding:0">'+(s.bullets||[]).map(b=>'<li style="margin:3px 0">'+esc(b)+'</li>').join('')+'</ul></details>').join('');
  if(n.proposed_change){const pc=n.proposed_change;
    h+='<div class="banner info" style="margin-top:8px">Proposed plan update — DRAFT, requires explicit application: '
     +(pc.changed?(pc.moves||[]).map(m=>esc(m.field)+' '+esc(fmtV(m.from))+' → '+esc(fmtV(m.to))).join(' · '):esc(pc.note))+'</div>'}
  h+='<div class="mut" style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:10px 0 4px">Evidence cited</div>'
   +'<table><thead><tr><th>Evidence</th><th>Value</th><th>Source</th><th>As of</th></tr></thead><tbody>'
   +(n.evidence_refs||[]).map(r=>'<tr><td>'+esc(r.label)+'</td><td>'+esc(typeof r.value==='object'?JSON.stringify(r.value):r.value)+'</td>'
     +'<td class="mut">'+esc(r.source)+'</td><td class="mut">'+esc(String(r.as_of||'').slice(0,19))+'</td></tr>').join('')+'</tbody></table>'
   +'<div class="mut" style="margin-top:8px;font-size:11.5px">This note cannot: '+esc((n.cannot||[]).join(', '))+'.</div>'
   +'<div class="row" style="margin-top:9px">'+Object.keys(CMD_LABEL).map(function(c){return '<button class="ghost" onclick="noteRun(&quot;'+c+'&quot;)">'+esc(CMD_LABEL[c])+'</button>'}).join('')+'</div>'
   +'<div id="noteoutbox" style="margin-top:8px"></div>';
  return h;
}
function renderCommandOut(d){
  if(!d||!d.ok){return '<div class="banner err">'+esc((d&&d.error)||'command failed')+'</div>'}
  return '<div class="banner info"><b>'+esc(d.title)+'</b></div>'
   +'<ul style="margin:6px 0 2px 18px;padding:0">'+(d.bullets||[]).map(b=>'<li style="margin:3px 0">'+esc(b)+'</li>').join('')+'</ul>';
}

let SCAN=null, CTX=null, SELECTED=null, CHART=null, SECTORS=null;
const DEFAULT_SYMS='SPY QQQ AAPL MSFT NVDA TSLA AMD META AMZN GOOGL';
function ctxCard(d){
  $('#ctxstamp').textContent='as of '+exStamp(d.generated_at)+' · '+exSession().replace('_',' ').toLowerCase();
  $('#ctx').innerHTML=d.proxies.map(p=>kpi(p.label,p.last==null?'—':num(p.last,2),pctS(p.change_pct)+' · '+p.quote_source,cls(p.change_pct))).join('')
   +kpi('Regime',d.regime,'avg '+pctS(d.average_change_pct),d.regime==='RISK-ON'?'up':d.regime==='RISK-OFF'?'dn':'')
   +kpi('Data freshness',d.freshness,d.freshness==='FRESH'?'live Schwab quotes':'cache only',d.freshness==='FRESH'?'up':'warn');
}
function sectorsCard(d){
  const secs=d.sectors||[];
  $('#secstamp').innerHTML=esc(d.ranked+'/'+d.declared+' ranked')
    +(secs.length&&secs[0].coverage?' <span class="mut">· universe: '+esc(secs[0].coverage)+'</span>':'');
  if(!secs.length){$('#sectors').innerHTML='<span class="mut">No sector data.</span>';return}
  // A compact ranked strip: one line per sector, RS expressed as a SHAPE rather than
  // three separate columns, and every row clickable through to the explorer.
  $('#sectors').innerHTML='<div class="secstrip">'+secs.map(function(r){
    const q=r.quadrant||'—';
    const qc=q==='LEADING'?'up':(q==='LAGGING'?'dn':(q==='WEAKENING'||q==='IMPROVING'?'warn':''));
    return '<button class="secrow" onclick="exFromSector(&quot;'+esc(r.symbol)+'&quot;)" title="'
      +esc(r.sector+' · '+q+' · 5d '+num(r.rs_5d,2)+' 20d '+num(r.rs_20d,2)+' 60d '+num(r.rs_60d,2))+'">'
      +'<span class="secrank">'+esc(r.rank)+'</span>'
      +'<span class="secsym">'+esc(r.symbol)+'</span>'
      +'<span class="secname">'+esc(r.sector)+'</span>'
      +'<span class="secq '+qc+'">'+esc(q)+'</span>'
      +'<span class="secspark">'+rsSpark(r.rs_5d,r.rs_20d,r.rs_60d)+'</span>'
      +'<span class="secshape">'+esc(rsShape(r.rs_5d,r.rs_20d,r.rs_60d))+'</span>'
      +'<span class="sec20 '+(r.rs_20d==null?'':(r.rs_20d>0?'up':'dn'))+'">'
        +(r.rs_20d==null?'—':(r.rs_20d>0?'+':'')+num(r.rs_20d,2)+'%')+'</span></button>';
  }).join('')+'</div>';
}
// Three horizon values -> a 3-point sparkline (shape at a glance).
function rsSpark(a,b,c){
  const v=[a,b,c];
  if(v.some(x=>x==null))return '<span class="mut">—</span>';
  const min=Math.min.apply(null,v), max=Math.max.apply(null,v), span=(max-min)||1;
  const pts=v.map(function(x,i){return (i*20+2)+','+(20-((x-min)/span)*16).toFixed(1)}).join(' ');
  const rising=c>b&&b>a, falling=c<b&&b<a;
  const tone=rising?'--up':(falling?'--dn':'--mut');
  return '<svg width="40" height="16" viewBox="0 0 44 22" aria-hidden="true"><polyline points="'+pts
    +'" fill="none" stroke="var('+tone+')" stroke-width="2"/></svg>';
}
// One word for what the three horizons mean together.
function rsShape(a,b,c){
  if(a==null||b==null||c==null)return 'no data';
  if(c>b&&b>a)return 'accelerating';
  if(c<b&&b<a)return 'fading';
  if(b>0&&c>0&&a<=0)return 'turning up';
  if(b<0&&c<0)return 'persistently weak';
  if(b>0&&c<b)return 'cooling';
  return 'mixed';
}
// Sector strip -> explorer, so the ranking and the drill-down are one object.
function exFromSector(sym){
  const el=document.querySelector('#exuniverse');
  if(el){exploreSector(sym);document.querySelector('#excatalog').scrollIntoView({behavior:'smooth',block:'start'})}
}
async function loadContext(){
  try{ CTX=await j('/api/context'); ctxCard(CTX);}catch(e){ $('#ctx').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'; }
  try{ SECTORS=await j('/api/sectors'); sectorsCard(SECTORS); }catch(e){ $('#sectors').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'; }
}
async function scan(){
  const syms=($('#syms').value||DEFAULT_SYMS).split(/[\s,]+/).filter(Boolean);
  const tf=$('#tf').value;
  $('#results').innerHTML='<span class="mut">Scanning '+syms.length+' symbols…</span>';
  try{
    SCAN=await j('/api/scan?timeframe='+tf+'&symbols='+encodeURIComponent(syms.join(',')));
    renderScan();
  }catch(e){ $('#results').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'; }
}
function filtered(){
  if(!SCAN)return [];
  const fs=$('#fside').value, fst=$('#fstate').value, fq=$('#fsym').value.trim().toUpperCase();
  return SCAN.results.filter(r=>{
    const st=setupState(r);
    if(fst&&st!==fst)return false;
    if(fs==='WAIT'){ if(r.side)return false; } else if(fs&&r.side!==fs)return false;
    if(fq&&!(r.symbol||'').includes(fq))return false;
    return true;
  });
}
function renderScan(){
  const rows=filtered();
  const actionable=(SCAN.results||[]).filter(r=>r.side);
  $('#rulever').textContent=SCAN.rule_version+' · '+(SCAN.timeframe==='15m'?'15m intraday':'daily swing');
  $('#verdict').innerHTML=(SCAN.verdict==='NO_QUALIFIED_TRADE')
    ? '<div class="banner">NO_QUALIFIED_TRADE — nothing passed the gates for this scan. No recommendation is forced.</div>'
    : '<div class="banner info">'+actionable.length+' qualified setup(s) · benchmark '+esc(SCAN.benchmark)+' ('+esc(SCAN.benchmark_source)+') · '+esc(String(SCAN.symbols))+' scanned'+(SCAN.errors?(' · '+SCAN.errors+' symbol(s) without data'):'')+'</div>';
  $('#rcount').textContent=rows.length+' shown';
  const bull=rows.filter(r=>r.side==='LONG'), bear=rows.filter(r=>r.side==='SHORT'), rest=rows.filter(r=>!r.side);
  const cols=[{h:'Sym',f:r=>'<b>'+esc(r.symbol)+'</b>'},{h:'State',f:r=>'<span class="chip '+setupState(r)+'">'+setupState(r)+'</span>'},
    {h:'Signal',f:r=>'<span class="chip '+esc(r.side||'WAIT')+'">'+esc(r.signal)+'</span>'},
    {h:'Score',num:1,f:r=>r.score==null?'—':num(r.score,1)},{h:'Entry',num:1,f:r=>num(r.entry,2)},
    {h:'Ref stop',num:1,f:r=>r.invalidation==null?'—':num(r.invalidation,2)},
    {h:'Target',num:1,f:r=>r.target==null?'—':num(r.target,2)},{h:'R:R plan',num:1,f:r=>r.risk_reward==null?'—':num(r.risk_reward,2)},
    {h:'Src',f:r=>'<span class="mut">'+esc(r.source||'')+'</span>'}];
  function block(title,list,empty){return '<div style="margin-bottom:10px"><div class="mut" style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:2px 0 4px">'+title+' ('+list.length+')</div>'+
    (list.length?table(cols,list,empty):'<span class="mut">'+esc(empty)+'</span>')+'</div>'}
  // Bearish rows are NOT a peer of the bullish ones: measured -0.60R vs +0.41R.
  // Label them unproven rather than letting the two blocks imply symmetry.
  const bearNote=bear.length?('<div class="banner" style="margin:0 0 8px">UNPROVEN — short signals measured at '
    +'<b>-0.60 R</b> per trade (PF 0.53) over a 2-year backtest, against <b>+0.41 R</b> (PF 1.37) for the long side. '
    +'The logic is symmetric with the long side, so this is market drift, not a bug: a regime gate allowing shorts only in '
    +'falling markets was tested and made results <i>worse</i>. Informational only — not tradeable setups.</div>'):'';
  $('#results').innerHTML=(!rows.length)?'<span class="mut">No rows match the filters.</span>'
    :(block('Bullish',bull,'none')+bearNote+block('Bearish — UNPROVEN',bear,'none')+block('Not qualified',rest,'none'));
  document.querySelectorAll('#results tbody tr').forEach(tr=>{
    const sym=tr.querySelector('b'); if(!sym)return;
    tr.style.cursor='pointer';
    tr.onclick=()=>select(sym.textContent);
  });
}
async function select(symbol){
  const row=(SCAN.results||[]).find(r=>r.symbol===symbol); if(!row)return;
  SELECTED=row; CHART=null;
  renderSelected();
  try{ CHART=await j('/api/chart?symbol='+encodeURIComponent(symbol)+'&timeframe='+(SCAN.timeframe||'1d')); }catch(e){}
  renderSelected();
}
function sparkline(chart,row){
  const host=document.getElementById('chartbox');
  if(!host)return;
  host.innerHTML='';
  if(!chart||!chart.closes||chart.closes.length<5){host.innerHTML='<span class="mut">chart unavailable</span>';return}
  const NS='http://www.w3.org/2000/svg';
  const c=chart.closes, w=520,h=150,pad=30;
  const levels=[row.entry,row.invalidation,row.target].filter(v=>typeof v==='number'&&isFinite(v)).concat(c);
  const lo=Math.min.apply(null,levels), hi=Math.max.apply(null,levels), span=(hi-lo)||1;
  const X=i=>pad+i*(w-pad*2)/(c.length-1);
  const Y=v=>h-pad-((v-lo)/span)*(h-pad*2);
  const svg=document.createElementNS(NS,'svg');
  svg.setAttribute('viewBox','0 0 '+w+' '+h);
  svg.setAttribute('preserveAspectRatio','none');
  svg.setAttribute('style','width:100%;height:150px;background:#0b1120;border:1px solid var(--line);border-radius:8px');
  const path=document.createElementNS(NS,'path');
  path.setAttribute('d',c.map((v,i)=>(i?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1)).join(' '));
  path.setAttribute('fill','none');
  path.setAttribute('stroke','#4c8dff');
  path.setAttribute('stroke-width','1.6');
  path.setAttribute('vector-effect','non-scaling-stroke');
  svg.appendChild(path);
  function level(v,color,label){
    if(typeof v!=='number'||!isFinite(v))return;
    const ln=document.createElementNS(NS,'line');
    ln.setAttribute('x1','0');ln.setAttribute('x2',w);ln.setAttribute('y1',Y(v).toFixed(1));ln.setAttribute('y2',Y(v).toFixed(1));
    ln.setAttribute('stroke',color);ln.setAttribute('stroke-width','1');ln.setAttribute('stroke-dasharray','5 4');
    ln.setAttribute('vector-effect','non-scaling-stroke');
    svg.appendChild(ln);
    const tx=document.createElementNS(NS,'text');
    tx.setAttribute('x','4');tx.setAttribute('y',(Y(v)-3).toFixed(1));
    tx.setAttribute('fill',color);tx.setAttribute('font-size','10');
    tx.textContent=label+' '+v.toFixed(2);
    svg.appendChild(tx);
  }
  level(row.entry,'#8b95ae','entry');level(row.invalidation,'#e5544b','invalid');level(row.target,'#26c281','target');
  const cap=document.createElementNS(NS,'text');
  cap.setAttribute('x','4');cap.setAttribute('y','13');
  cap.setAttribute('fill','#8b95ae');cap.setAttribute('font-size','10');
  cap.textContent=chart.symbol+' - '+c.length+' bars - '+chart.source;
  svg.appendChild(cap);
  host.appendChild(svg);
  const legend=document.getElementById('chartlegend');
  if(legend)legend.textContent='entry '+num(row.entry,2)+' | invalidation '+num(row.invalidation,2)+
    ' | target '+num(row.target,2)+' | '+c.length+' bars ('+chart.source+')';
}
function renderSelected(){
  const r=SELECTED; if(!r){return}
  $('#selstate').innerHTML='<span class="chip '+setupState(r)+'">'+setupState(r)+'</span>';
  if(r.error){ $('#sel').innerHTML='<div class="banner err">'+esc(r.symbol)+': '+esc(r.error)+'</div>'; return; }
  const f=r.factors||{};
  const maxAbs=Math.max.apply(null,Object.values(f).concat([100]));
  let h='<div class="row" style="justify-content:space-between;margin-bottom:8px">'
   +'<div><b style="font-size:16px">'+esc(r.symbol)+'</b> <span class="chip '+esc(r.side||'WAIT')+'">'+esc(r.signal)+'</span></div>'
   +'<div class="mut">quote '+esc(r.quote_source||'')+' · bars '+esc(r.source||'')+(r.quote&&r.quote.realtime?' · realtime':'')+'</div></div>';
  h+='<div class="kpis" style="margin-bottom:9px">'
   +kpi('Score',r.score==null?'—':num(r.score,1),'thresholds 70 / 30',cls((r.score||50)-50))
   +kpi('Last',money(r.last),'as of scan')
   +kpi('Entry',money(r.entry),'plan reference')
   +kpi('Ref. stop',money(r.invalidation),'REFERENCE — not enforced','dn')
   +kpi('Target',money(r.target),'1.8R','up')
   +kpi('R:R plan',r.risk_reward==null?'—':num(r.risk_reward,2),'configured — realised long +0.41R')
   +kpi('ATR',r.atr==null?'—':num(r.atr,2),'14-period')+'</div>';
  h+='<div id="chartbox" style="margin-top:4px"><span class="mut">chart loading…</span></div>'
   +'<div class="mut" id="chartlegend" style="font-size:11.5px;margin-top:5px"></div>';
  h+='<div style="margin-top:10px"><div class="mut" style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Score breakdown</div>'
   +'<table><thead><tr><th>Factor</th><th class="num">Value</th><th>Weight</th><th>Contribution</th></tr></thead><tbody>'
   +Object.entries(f).map(([k,v])=>{const w={SMC:.25,Phases:.20,CVD_Absorption:.20,VScore:.15,RS_Rank:.10,OptionsFlow:.10}[k]||0;
     return '<tr><td>'+esc(k)+'</td><td class="num">'+num(v,1)+'</td><td class="mut">'+w.toFixed(2)+'</td>'
      +'<td>'+bar(v,100)+'</td><td class="num">'+num(v*w,1)+'</td></tr>'}).join('')
   +'</tbody></table></div>';
  if((r.alerts||[]).length) h+='<div class="mut" style="margin-top:8px;font-size:12px">Gates triggered: '+r.alerts.map(esc).join(' · ')+'</div>';
  else h+='<div class="mut" style="margin-top:8px;font-size:12px">No factor crossed its gate.</div>';
  h+='<details style="margin-top:11px;border-top:1px solid var(--line);padding-top:9px"><summary style="cursor:pointer"><b>AI trade notes</b> <span class="mut">evidence-grounded · versioned · self-invalidating</span></summary>'
   +'<div style="margin-top:8px"><div class="row"><button onclick="loadNotes()">Generate / refresh notes</button>'
   +'<span class="mut" style="font-size:11.5px">deterministic — cites evidence and cannot alter scores or orders</span></div>'
   +'<div id="notesbody" style="margin-top:9px"><span class="mut">Generate notes from the captured evidence.</span></div></div></details>';
  h+='<div class="row" style="margin-top:11px"><button onclick="openTrade()">Open Trade Workspace →</button>'
   +'<span class="mut" style="font-size:11.5px">carries this setup (snapshot) to the order ticket</span></div>';
  $('#sel').innerHTML=h;
  sparkline(CHART,r);
}
function setupSnapshot(){
  if(!SELECTED)return null;
  return {setup_id:SELECTED.symbol+'-'+(SCAN.timeframe||'1d')+'-'+(SELECTED.side||'WAIT'),
    setup_version:1, symbol:SELECTED.symbol, side:SELECTED.side, score:SELECTED.score, signal:SELECTED.signal,
    entry:SELECTED.entry, invalidation:SELECTED.invalidation, target:SELECTED.target,
    risk_reward:SELECTED.risk_reward, factors:SELECTED.factors, source:SELECTED.source,
    quote_source:SELECTED.quote_source, quote:SELECTED.quote, atr:SELECTED.atr,
    timeframe:SCAN.timeframe||'1d', rule_version:SCAN.rule_version,
    publication_state:'RESEARCH_ONLY', executable:false, captured_at:new Date().toISOString()};
}
function openTrade(){
  const snap=setupSnapshot(); if(!snap)return;
  try{localStorage.setItem('qx.selectedSetup',JSON.stringify(snap))}catch(e){}
  location.href='/trade';
}
$('#syms').value=DEFAULT_SYMS;
$('#tf').addEventListener('change',scan);
['#fside','#fstate','#fsym'].forEach(s=>{$(s).addEventListener('input',renderScan);$(s).addEventListener('change',renderScan)});
function sectorFor(sym){return SECTORS?((SECTORS.sectors||[]).find(s=>s.symbol===sym)||null):null}
async function loadNotes(){
  if(!SELECTED)return;
  $('#notesbody').innerHTML='<span class="mut">Generating notes…</span>';
  try{
    const d=await j('/api/notes',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({setup:setupSnapshot(),context:CTX,sector:sectorFor(SELECTED.symbol),peers:(SCAN.results||[])})});
    $('#notesbody').innerHTML=notesHtml(d);
  }catch(e){$('#notesbody').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
async function noteRun(cmd){
  const box=document.getElementById('noteoutbox');
  if(box){box.innerHTML='<span class="mut">Running '+esc(cmd)+'…</span>';}
  try{
    const d=await j('/api/notes/command',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({command:cmd,setup:setupSnapshot(),context:CTX,sector:sectorFor(SELECTED.symbol),
        peers:(SCAN.results||[]),include_outcome:cmd==='review-completed-trade'})});
    const target=document.getElementById('noteoutbox');
    if(target){target.innerHTML=renderCommandOut(d);}else if(box){box.innerHTML=renderCommandOut(d);}
  }catch(e){
    const target=document.getElementById('noteoutbox');
    if(target)target.innerHTML='<div class="banner err">'+esc(e.message)+'</div>';
  }
}
loadContext().then(scan);
