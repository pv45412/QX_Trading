"""QX application shell and pages (self-contained HTML/CSS/JS, no external assets)."""

APP_CSS = """
:root{--bg:#0a0e18;--panel:#101827;--panel2:#0d1523;--line:#22304a;--fg:#e8edf7;--mut:#8b95ae;
--up:#26c281;--dn:#e5544b;--acc:#4c8dff;--warn:#e0a83c;--ok:#26c281}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.5 system-ui,"Segoe UI",sans-serif}
header.top{display:flex;align-items:center;gap:18px;padding:11px 18px;border-bottom:1px solid var(--line);
background:linear-gradient(180deg,#0d1524,#0a0e18);position:sticky;top:0;z-index:20}
.brand{font-weight:700;font-size:15px;letter-spacing:.02em}
.brand em{color:var(--mut);font-weight:400;font-style:normal;font-size:11px;margin-left:6px}
nav{display:flex;gap:4px}
nav a{color:var(--mut);text-decoration:none;padding:6px 12px;border-radius:7px;font-weight:600;font-size:12.5px}
nav a:hover{background:#16203200;color:var(--fg);background:#17213a}
nav a.on{background:#17213a;color:var(--fg)}
.spacer{flex:1}
.modebadge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;background:rgba(224,168,60,.15);color:var(--warn)}
.wrap{max-width:1500px;margin:0 auto;padding:16px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px;margin:11px 0}
.card h2{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--mut);margin:0 0 10px;
display:flex;justify-content:space-between;align-items:center;gap:8px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px}
.kpi{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:9px 11px}
.kpi span{display:block;color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em}
.kpi b{display:block;font-size:17px;margin-top:3px;font-variant-numeric:tabular-nums}
.kpi em{display:block;color:var(--mut);font-size:10.5px;font-style:normal;margin-top:2px}
.up{color:var(--up)}.dn{color:var(--dn)}.mut{color:var(--mut)}.warn{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:#0e1729}
tbody tr.sel{background:#152342}
.grid2{display:grid;grid-template-columns:1.35fr 1fr;gap:11px}
@media(max-width:1050px){.grid2{grid-template-columns:1fr}}
select,input,button{background:#0d1526;border:1px solid var(--line);color:var(--fg);border-radius:7px;padding:6px 9px;font:inherit}
input[type=checkbox]{width:auto}
button{cursor:pointer;background:var(--acc);border:0;color:#fff;font-weight:600}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg);font-weight:500}
button.danger{background:var(--dn)}
button:disabled{opacity:.45;cursor:not-allowed}
.chip{display:inline-block;padding:1px 7px;border-radius:999px;font-size:10.5px;font-weight:700;background:#1b2740;color:var(--mut)}
.chip.LONG,.chip.BUY,.chip.QUALIFIED_RESEARCH,.chip.FRESH{background:rgba(38,194,129,.16);color:var(--up)}
.chip.SHORT,.chip.SELL{background:rgba(229,84,75,.16);color:var(--dn)}
.chip.ARMED{background:rgba(224,168,60,.16);color:var(--warn)}.chip.QUALIFIED_RESEARCH{background:rgba(76,141,255,.16);color:var(--acc)}
.chip.WAIT,.chip.WATCH{background:#1b2740;color:var(--mut)}
.chip.LEADING{background:rgba(38,194,129,.16);color:var(--up)}
.chip.LAGGING{background:rgba(229,84,75,.14);color:var(--dn)}
.chip.IMPROVING{background:rgba(76,141,255,.16);color:var(--acc)}
.chip.WEAKENING{background:rgba(224,168,60,.14);color:var(--warn)}
.banner{border-left:3px solid var(--warn);background:rgba(224,168,60,.08);padding:8px 11px;border-radius:6px;
color:var(--warn);font-size:12px;margin:9px 0}
.banner.err{border-color:var(--dn);background:rgba(229,84,75,.08);color:var(--dn)}
.banner.ok{border-color:var(--ok);background:rgba(38,194,129,.08);color:var(--ok)}
.banner.info{border-color:var(--acc);background:rgba(76,141,255,.07);color:var(--fg)}
.bar{height:8px;border-radius:3px;background:#1b2740;overflow:hidden;min-width:54px}
.bar i{display:block;height:100%}
.scroll{max-height:360px;overflow:auto;border:1px solid var(--line);border-radius:8px}
/* Sector strip: one compact clickable line per sector instead of a tall table. */
.secstrip{display:grid;grid-template-columns:1fr 1fr;gap:1px 18px}
.secrow{display:grid;grid-template-columns:20px 46px minmax(90px,1fr) 84px 46px 88px 64px;
  align-items:center;gap:7px;width:100%;text-align:left;background:none;border:0;
  border-radius:5px;padding:1px 6px;color:var(--fg);cursor:pointer;font:inherit;font-size:12px;line-height:1.5}
.secrow:hover{background:rgba(76,141,255,.10)}
.secrank{color:var(--mut);font-variant-numeric:tabular-nums;text-align:right}
.secsym{font-weight:600;letter-spacing:.01em}
.secname{color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.secq{font-size:10px;text-transform:uppercase;letter-spacing:.05em}
.secq.up{color:var(--up)}.secq.dn{color:var(--dn)}.secq.warn{color:var(--warn)}
.secspark{display:flex;align-items:center}
.secspark svg{height:16px;width:40px}
.secshape{color:var(--mut);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sec20{text-align:right;font-variant-numeric:tabular-nums}
.two{display:grid;grid-template-columns:1fr 1fr;gap:11px}
@media(max-width:900px){.two{grid-template-columns:1fr}}
.f-row{display:grid;grid-template-columns:110px 1fr;gap:8px;align-items:center;margin-bottom:7px}
.f-row label{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
ul.checks{list-style:none;margin:0;padding:0}
ul.checks li{padding:5px 8px;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:flex-start}
ul.checks li b{flex:0 0 22px}
pre.payload{background:#0b1120;border:1px solid var(--line);border-radius:7px;padding:9px;
overflow:auto;font-size:11.5px;max-height:210px;margin:0}
kbd{background:#1b2740;border-radius:4px;padding:1px 5px;font-size:11px}
.stale{color:var(--warn)}
/* ---- responsive ---- */
@media(max-width:760px){
  header.top{flex-wrap:wrap;gap:8px;padding:9px 12px}
  nav{flex-wrap:wrap;gap:2px}
  nav a{padding:6px 9px;font-size:12px}
  .modebadge{font-size:10px;padding:3px 7px}
  .wrap{padding:11px}
  h1{font-size:16px}
  .kpis{grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:7px}
  .kpi b{font-size:15px}
  /* Inputs and selects must be allowed to shrink inside their flex row. */
  .row{gap:7px}
  .row>input,.row>select{flex:1 1 130px;min-width:0;width:auto}
  #syms{width:auto!important}
  .f-row{grid-template-columns:88px 1fr}
  .card{padding:11px}
  table{font-size:11.5px}
  th,td{padding:5px 6px}
  .scroll{max-height:300px}
  .two,.grid2{grid-template-columns:1fr}
}
@media(max-width:480px){
  .kpis{grid-template-columns:1fr 1fr}
  .kpi{padding:7px 9px}
  .kpi b{font-size:14px}
  .row>input,.row>select{flex:1 1 100%}
  nav a{font-size:11.5px;padding:5px 8px}
}
/* Long tables scroll inside their card rather than widening the page. */
.scroll{overflow-x:auto}
/* Any table wrapper must clip rather than push the page wide. */
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{min-width:0}
.card{overflow-x:auto}
"""

NAV = """
<header class="top">
  <div class="brand">QX<em>trading workspace</em></div>
  <nav id="nav">
    <a href="/scanner" data-nav="scanner">Discover</a>
    <a href="/ideas" data-nav="ideas">Trade Ideas</a>
    <a href="/trade" data-nav="trade">Trade Workspace</a>
    <a href="/context" data-nav="context">Context</a>
    <a href="/reports" data-nav="reports">Reports</a>
    <a href="/settings" data-nav="settings">Settings</a>
  </nav>
  <div class="spacer"></div>
  <span class="mut" id="clock" style="font-size:11.5px"></span>
  <span class="modebadge" id="livemode">LIVE EXECUTION DISABLED · SIMULATED ONLY</span>
</header>
<script>
document.querySelectorAll('#nav a').forEach(function(a){
  if(a.getAttribute('href')===location.pathname){a.classList.add('on')}
});
// Exchange clock, so every page shows market time rather than the host's zone.
(function(){
  const el=document.getElementById('clock');
  if(!el)return;
  const fmt=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour12:false,
    hour:'2-digit',minute:'2-digit',second:'2-digit'});
  function tick(){
    const s=document.getElementById('clock'); if(!s)return;
    const d=new Date();
    const p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',
      hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d);
    const get=t=>(p.find(x=>x.type===t)||{}).value;
    const wd=get('weekday'), hh=Number(get('hour'))%24, mm=Number(get('minute'));
    let st='CLOSED';
    if(wd==='Sat'||wd==='Sun')st='CLOSED_WEEKEND';
    else{const m=hh*60+mm; st=m<570?'PRE_MARKET':m<960?'REGULAR':m<1200?'AFTER_HOURS':'CLOSED'}
    const tone=st==='REGULAR'?'var(--up)':(st==='PRE_MARKET'||st==='AFTER_HOURS'?'var(--warn)':'var(--mut)');
    s.innerHTML=fmt.format(d)+' ET <span style="color:'+tone+'">· '+st.replace('_',' ').toLowerCase()+'</span>';
  }
  tick(); setInterval(tick,1000);
})();
</script>
"""


def shell(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>"
        f"<title>{title}</title><style>{APP_CSS}</style></head><body>"
        f"{NAV}<div class=\"wrap\">{body}</div></body></html>"
    )


# --------------------------------------------------------------------------- #
# Shared JS helpers
# --------------------------------------------------------------------------- #

HELPERS = """
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
"""

# Deterministic setup-state derivation. Reviewer F04: the browser must NEVER
# derive an execution label. EXECUTABLE is owned solely by the server's
# validate_execution_eligibility gate; this projection reports research state only.
SETUP_STATE_JS = """
function setupState(row){
  if(row.error)return 'WATCH';
  const s=row.score; if(s==null)return 'WATCH';
  // Research projection only. Directional score labels are deliberately distinct
  // from execution labels; EXECUTABLE is never produced here.
  if(row.side)return 'QUALIFIED_RESEARCH';
  if(Math.abs(s-70)<=5||Math.abs(s-30)<=5)return 'ARMED';
  return 'WATCH';
}
"""

NOTES_JS = """
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
"""


# --------------------------------------------------------------------------- #
# PAGE 1 — Scanner
# --------------------------------------------------------------------------- #

SCANNER_BODY = """
<div class="row" style="justify-content:space-between">
  <h1 style="font-size:17px;margin:0">Scanner <span class="mut" style="font-size:12px" id="rulever"></span></h1>
  <div class="row">
    <select id="tf"><option value="1d" selected>Swing (daily)</option><option value="15m">Intraday (15m)</option></select>
    <input id="syms" style="flex:1 1 200px;min-width:0" placeholder="symbols (space/comma separated)"/>
    <button onclick="scan()">Scan</button>
  </div>
</div>
<div id="verdict"></div>
<div class="card"><h2>Market context <span class="mut" id="ctxstamp"></span></h2><div class="kpis" id="ctx"><span class="mut">Loading…</span></div></div>
<div class="card"><h2>Sector rankings <span class="mut" id="secstamp"></span></h2><div id="sectors"><span class="mut">Loading…</span></div></div>
<div class="grid2">
  <div class="card"><h2>Results</h2>
    <div class="row" style="margin-bottom:8px">
      <select id="fside"><option value="">All sides</option><option>LONG</option><option>SHORT</option><option value="WAIT">WAIT only</option></select>
      <select id="fstate"><option value="">All states</option><option>QUALIFIED_RESEARCH</option><option>ARMED</option><option>WATCH</option></select>
      <input id="fsym" style="flex:0 1 120px;min-width:0" placeholder="filter symbol"/>
      <span class="mut" id="rcount"></span>
    </div>
    <div class="scroll" id="results"><span class="mut">Run a scan.</span></div>
  </div>
  <div class="card"><h2>Selected setup <span class="mut" id="selstate"></span></h2>
    <div id="sel"><span class="mut">Select a row to inspect its plan, chart and gates.</span></div>
  </div>
</div>
<script>
""" + HELPERS + SETUP_STATE_JS + NOTES_JS + """
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
  const syms=($('#syms').value||DEFAULT_SYMS).split(/[\\s,]+/).filter(Boolean);
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
</script>
"""


# --------------------------------------------------------------------------- #
# PAGE 2 — Trade Workspace
# --------------------------------------------------------------------------- #

TRADE_BODY = """
<div class="row" style="justify-content:space-between">
  <h1 style="font-size:17px;margin:0">Trade Workspace</h1>
  <div class="row">
    <select id="acct"></select>
    <button class="ghost" onclick="loadAccount()">Refresh account</button>
  </div>
</div>
<div class="banner err" id="livegate">Live order submission is DISABLED (governance: EX0–EX3 human gates). This page places <b>application-level simulated</b> orders only — nothing is sent to Schwab.</div>
<div id="acctwarn"></div>
<div class="card"><h2>Account <span class="mut" id="acctstamp"></span></h2><div class="kpis" id="acctkpi"><span class="mut">Loading…</span></div></div>
<div class="two">
  <div class="card"><h2>Positions</h2><div id="positions"><span class="mut">—</span></div></div>
  <div class="card"><h2>Open orders <span class="mut" id="oostamp"></span></h2><div id="openorders"><span class="mut">—</span></div></div>
</div>
<div class="grid2">
  <div class="card"><h2>Order ticket <span class="mut" id="setupbadge"></span></h2>
    <div class="two">
      <div>
        <div class="f-row"><label>Symbol</label><input id="t_sym" placeholder="e.g. AAPL"/></div>
        <div class="f-row"><label>Side</label><select id="t_side"><option>BUY</option><option>SHORT</option></select></div>
        <div class="f-row"><label>Quantity</label><input id="t_qty" type="number" min="0" step="1" value="100"/></div>
      </div>
      <div>
        <div class="f-row"><label>Type</label><select id="t_type"><option>LIMIT</option><option>MARKET</option></select></div>
        <div class="f-row"><label>Limit</label><input id="t_limit" type="number" step="0.01" placeholder="price"/></div>
        <div class="f-row"><label>Duration</label><select id="t_dur"><option>DAY</option><option>GTC</option></select></div>
      </div>
    </div>
    <div class="row"><button onclick="review()">Review order</button>
      <button class="ghost" onclick="clearSetup()">Clear setup</button>
      <span class="mut" id="tnote"></span></div>
  </div>
  <div class="card"><h2>Local review <span class="mut" id="verdictbadge"></span></h2><div id="review"><span class="mut">Review the ticket to see the exact proposed order and its checks.</span></div></div>
</div>
<details class="card" id="notescard"><summary style="cursor:pointer"><b>AI trade notes</b> <span class="mut" id="notessetup">no setup carried</span></summary>
  <div class="row" style="margin-top:8px"><button onclick="loadTradeNotes()">Generate / refresh notes</button>
    <span class="mut" style="font-size:11.5px">carried setup · deterministic · cites evidence · cannot alter the ticket</span></div>
  <div id="notesbody" style="margin-top:9px"><span class="mut">Open a setup from the Scanner to attach notes.</span></div>
</details>
<div class="card"><h2>Simulated orders <span class="mut" id="ordstamp"></span></h2><div id="orders"><span class="mut">—</span></div></div>
<script>
""" + HELPERS + NOTES_JS + """
let ACCOUNTS=[], DETAIL=null, SETUP=null, REVIEW=null;
function money0(v){return v==null?'—':money(v)}
function setupBadge(){
  if(!SETUP){$('#setupbadge').textContent='no setup attached (free-form)';}
  else{$('#setupbadge').innerHTML='<span class="chip '+esc(SETUP.side||'WAIT')+'">'+esc(SETUP.signal||'')+'</span> '+esc(SETUP.symbol)+' v'+esc(SETUP.setup_version)+' · score '+esc(SETUP.score)+' · '+esc(SETUP.timeframe);}
  const ns=$('#notessetup'); if(ns)ns.textContent=SETUP?(SETUP.symbol+' · score '+SETUP.score+' · v'+SETUP.setup_version):'no setup carried';
}
async function loadTradeNotes(){
  if(!SETUP){$('#notesbody').innerHTML='<div class="banner">No setup is carried. Open one from the Scanner.</div>';return}
  $('#notesbody').innerHTML='<span class="mut">Generating notes…</span>';
  try{
    const d=await j('/api/notes',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({setup:SETUP})});
    $('#notesbody').innerHTML=notesHtml(d);
  }catch(e){$('#notesbody').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
async function noteRun(cmd){
  if(!SETUP){alert('No setup carried.');return}
  const box=document.getElementById('noteoutbox');
  if(box){box.innerHTML='<span class="mut">Running '+esc(cmd)+'…</span>';}
  try{
    const d=await j('/api/notes/command',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({command:cmd,setup:SETUP,ticket_validation:REVIEW,account:$('#acct').value,
        include_outcome:cmd==='review-completed-trade'})});
    const target=document.getElementById('noteoutbox');
    if(target)target.innerHTML=renderCommandOut(d);
  }catch(e){
    const target=document.getElementById('noteoutbox');
    if(target)target.innerHTML='<div class="banner err">'+esc(e.message)+'</div>';
  }
}
async function loadAccounts(){
  const d=await j('/api/trade/accounts'); ACCOUNTS=d.accounts||[];
  $('#acct').innerHTML=ACCOUNTS.map(a=>'<option value="'+esc(a.account_number)+'">'+esc(a.label)+' '+esc(a.masked)+'</option>').join('');
  $('#acctwarn').innerHTML=(d.warnings||[]).map(w=>'<div class="banner info">'+esc(w)+'</div>').join('');
  if(!ACCOUNTS.length){$('#acctkpi').innerHTML='<div class="banner err">No accounts readable by the token.</div>';return false}
  return true;
}
async function loadAccount(){
  const acct=$('#acct').value; if(!acct)return;
  $('#acctkpi').innerHTML='<span class="mut">Loading…</span>';
  try{
    DETAIL=await j('/api/trade/account?account='+encodeURIComponent(acct));
    const b=DETAIL.balances;
    $('#acctstamp').textContent=esc(DETAIL.account.masked)+' · '+esc(DETAIL.account.type)+' · as of '+exStamp(DETAIL.generated_at);
    $('#acctkpi').innerHTML=kpi('Equity',money(b.equity),'liquidation value')
      +kpi('Cash',money(b.cash),'available')
      +kpi('Buying power',money(b.buying_power),'')
      +kpi('Long market value',money(b.long_market_value),'')
      +kpi('Short market value',money(b.short_market_value),'');
    $('#positions').innerHTML=table([{h:'Symbol',f:r=>'<b>'+esc(r.symbol)+'</b>'},{h:'Type',f:r=>'<span class="chip">'+esc(r.asset_type)+'</span>'},
      {h:'Qty',num:1,f:r=>num(r.quantity,4)},{h:'Avg',num:1,f:r=>money(r.average_price)},
      {h:'Mkt value',num:1,f:r=>money(r.market_value)},{h:'Day P&L',num:1,f:r=>'<span class="'+cls(r.day_pnl)+'">'+money(r.day_pnl)+'</span>'}],
      DETAIL.positions,'No open positions.');
    $('#oostamp').textContent=DETAIL.open_orders_error?('· '+DETAIL.open_orders_error):('· '+(DETAIL.open_orders||[]).length+' open of '+(DETAIL.recent_orders_count||0)+' orders in 60d');
    $('#openorders').innerHTML=table([{h:'Entered',f:r=>esc(String(r.entered_time||'').slice(0,19).replace('T',' '))},
      {h:'Symbol',f:r=>esc(r.symbol||'—')},{h:'Instr',f:r=>esc(r.instruction||'—')},
      {h:'Type',f:r=>esc(r.order_type||'')},{h:'Qty',num:1,f:r=>num(r.quantity,0)},
      {h:'Filled',num:1,f:r=>num(r.filled_quantity,0)},{h:'Status',f:r=>'<span class="chip">'+esc(r.status||'')+'</span>'},
      {h:'Id',f:r=>'<span class="mut">'+esc(String(r.order_id||'').slice(-8))+'</span>'}],DETAIL.open_orders,'No orders in the last 60 days.');
  }catch(e){ $('#acctkpi').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'; }
}
function sizeFromSetup(){
  // Suggest a quantity that respects the 35%-of-equity concentration limit and
  // keeps risk-to-invalidation near 1% of equity. Never silently submits.
  if(!SETUP||!DETAIL)return;
  const eq=(DETAIL.balances&&DETAIL.balances.equity)||0;
  const px=Number($('#t_limit').value||SETUP.entry||0);
  if(!eq||!px)return;
  const byNotional=Math.floor((eq*0.20)/px);
  let qty=Math.max(1,byNotional);
  const inv=Number(SETUP.invalidation||0);
  if(inv&&Math.abs(px-inv)>0){
    const riskPerShare=Math.abs(px-inv);
    const byRisk=Math.floor((eq*0.01)/riskPerShare);
    if(byRisk>=1)qty=Math.max(1,Math.min(byNotional,byRisk));
  }
  if(qty>=1){$('#t_qty').value=qty;$('#tnote').innerHTML='<span class="mut">suggested size '+qty+' (20% notional cap, ~1% equity risk to invalidation)</span>';}
}
function readSetup(){
  try{ SETUP=JSON.parse(localStorage.getItem('qx.selectedSetup')||'null') }catch(e){ SETUP=null }
  setupBadge();
  if(SETUP){
    $('#t_sym').value=SETUP.symbol||''; $('#t_side').value=(SETUP.side==='SHORT')?'SHORT':'BUY';
    if(SETUP.entry){$('#t_limit').value=Number(SETUP.entry).toFixed(2)}
    sizeFromSetup();
  }
}
function clearSetup(){ localStorage.removeItem('qx.selectedSetup'); SETUP=null; setupBadge(); }
async function review(){
  const ticket={account:$('#acct').value, symbol:$('#t_sym').value.trim().toUpperCase(),
    side:$('#t_side').value, quantity:Number($('#t_qty').value||0), order_type:$('#t_type').value,
    limit_price:$('#t_limit').value===''?null:Number($('#t_limit').value), duration:$('#t_dur').value, setup:SETUP};
  $('#review').innerHTML='<span class="mut">Validating…</span>';
  try{
    REVIEW=await j('/api/trade/validate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(ticket)});
    renderReview();
  }catch(e){ $('#review').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'; }
}
function renderReview(){
  const v=REVIEW; if(!v)return;
  const ok=v.verdict==='READY_FOR_CONFIRMATION';
  // Drop any previously-armed confirmation so the gate can never leak across
  // renders: a checkbox from an earlier validation must not submit a new one.
  const prior=$('#okchk'); if(prior&&prior.parentNode){prior.checked=false;prior.parentNode.removeChild(prior);}
  const priorBtn=$('#subbtn'); if(priorBtn&&priorBtn.parentNode){priorBtn.parentNode.removeChild(priorBtn);}
  $('#verdictbadge').innerHTML='<span class="chip '+(ok?'QUALIFIED_RESEARCH':'WAIT')+'">'+esc(v.verdict)+'</span>';
  let h='<div class="banner '+(ok?'ok':'err')+'">'+(ok?'All local checks passed — confirmation required before staging.':'BLOCKED by: '+esc((v.failed||[]).join(', ')))+'</div>';
  h+='<pre class="payload">'+esc(JSON.stringify(v.proposed_order,null,2))+'</pre>';
  h+='<div class="kpis" style="margin:9px 0">'
   +kpi('Est. cost',money(v.estimated_cost),'qty × price')
   +kpi('Notional',v.notional_pct_of_equity==null?'—':num(v.notional_pct_of_equity,1)+'%','of equity')
   +kpi('Risk to invalidation',money(v.risk_to_invalidation),'from setup plan')
   +kpi('Ticket hash',esc(v.ticket_hash),'duplicate guard')+'</div>';
  h+='<div class="mut" style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:4px 0">Deterministic checks</div>';
  h+='<ul class="checks">'+v.checks.map(c=>'<li><b class="'+(c.passed?'up':'dn')+'">'+(c.passed?'✓':'✕')+'</b><span>'+esc(c.name)+' <span class="mut">— '+esc(c.detail)+'</span></span></li>').join('')+'</ul>';
  h+='<div class="banner info" style="margin-top:9px">Repo execution-eligibility gate (reported, not forged): <b>'+
     (v.ex_gate&&v.ex_gate.allowed===true?'ALLOWED':v.ex_gate&&v.ex_gate.allowed===false?'BLOCKED':'N/A')+'</b> — '+esc((v.ex_gate||{}).reason||'')+'</div>';
  // Submit stays disabled until the human ticks the box; the handler re-checks.
  h+='<div class="row" style="margin-top:11px"><label class="row" style="gap:6px"><input type="checkbox" id="okchk"'+(ok?'':' disabled')+' onchange="var b=document.getElementById(&quot;subbtn&quot;); if(b) b.disabled=!this.checked"/> I confirm this exact order</label>'
   +'<button id="subbtn" '+(ok?'disabled':'disabled')+' onclick="submitOrder()">Submit (simulated)</button>'
   +'<button class="danger" disabled title="gated">Submit live (disabled)</button></div>';
  $('#review').innerHTML=h;
}
async function submitOrder(){
  const chk=$('#okchk');
  if(!REVIEW||!chk||!chk.checked){alert('Tick "I confirm this exact order" first.');return}
  const btn=$('#subbtn'); if(btn){btn.disabled=true;btn.textContent='Submitting…'}
  try{
    const r=await j('/api/trade/orders',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({ticket:REVIEW.proposed_order, setup:SETUP, account:$('#acct').value, confirm:true, ticket_hash:REVIEW.ticket_hash})});
    $('#tnote').innerHTML=r.ok?('<span class="up">'+esc(r.order.intent_id)+' '+esc(r.order.status)+'</span>'):('<span class="dn">'+esc(r.error)+'</span>');
    if(!r.ok){if(btn){btn.disabled=false;btn.textContent='Submit (simulated)'}}
    await loadOrders();
  }catch(e){ $('#tnote').innerHTML='<span class="dn">'+esc(e.message)+'</span>'; if(btn){btn.disabled=false;btn.textContent='Submit (simulated)'} }
}
async function loadOrders(){
  try{
    const d=await j('/api/trade/orders');
    $('#ordstamp').textContent=d.count+' recorded · '+d.mode+(d.app_level?' (app-level)':'');
    $('#orders').innerHTML=table([{h:'Intent',f:r=>'<b>'+esc(r.intent_id)+'</b>'},
      {h:'Time',f:r=>esc(exTime(r.created_at,true))},
      {h:'Symbol',f:r=>esc(r.symbol)},{h:'Side',f:r=>'<span class="chip '+esc(r.side)+'">'+esc(r.side)+'</span>'},
      {h:'Qty',num:1,f:r=>num(r.quantity,0)},{h:'Type',f:r=>esc(r.order_type)},
      {h:'Limit',num:1,f:r=>r.limit_price==null?'—':money(r.limit_price)},
      {h:'Status',f:r=>'<span class="chip">'+esc(r.status)+'</span>'},
      {h:'Mode',f:r=>'<span class="mut">'+esc(r.mode)+'</span>'},
      {h:'',f:r=>(r.status==='FILLED'||r.status==='CANCELED')?'<span class="mut">—</span>':'<button class="ghost" onclick="cancelOrder(&quot;'+esc(r.intent_id)+'&quot;)">Cancel</button>'}],
      d.orders,'No simulated orders yet.');
  }catch(e){ $('#orders').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'; }
}
async function cancelOrder(id){
  try{ const r=await j('/api/trade/orders/cancel',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({intent_id:id})});
    if(!r.ok)alert(r.error); await loadOrders(); }catch(e){alert(e.message)}
}
$('#acct').addEventListener('change',loadAccount);
readSetup();
loadAccounts().then(ok=>{if(ok)loadAccount().then(sizeFromSetup)});
loadOrders();
</script>
"""


def reports_page() -> str:
    """Reuse the verified reporting dashboard, with the shared app nav injected."""
    from qx.reporting.dashboard import DASHBOARD_HTML

    extra_css = (
        "<style>.top{display:flex;align-items:center;gap:18px;padding:11px 18px;"
        "border-bottom:1px solid var(--line,#222f49);background:linear-gradient(180deg,#0d1524,#0a0e18);"
        "position:sticky;top:0;z-index:20;margin:-18px -18px 16px;flex-wrap:wrap}"
        ".top .brand{font-weight:700;font-size:15px}.top .brand em{color:#8b95ae;font-weight:400;"
        "font-style:normal;font-size:11px;margin-left:6px}"
        ".top nav{display:flex;gap:4px;flex-wrap:wrap}.top nav a{color:#8b95ae;text-decoration:none;padding:6px 12px;"
        "border-radius:7px;font-weight:600;font-size:12.5px}.top nav a:hover{background:#17213a;color:#e8edf7}"
        ".top nav a.on{background:#17213a;color:#e8edf7}.top .spacer{flex:1}"
        ".top .modebadge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;"
        "background:rgba(76,141,255,.14);color:#4c8dff}"
        # Tables in this dashboard are wider than a phone viewport, so the CARD scrolls
        # them internally instead of pushing the whole page sideways.
        ".card{overflow-x:auto;min-width:0}"
        ".card table{min-width:0}"
        "@media(max-width:900px){"
        ".top{gap:8px;padding:9px 12px;margin:-18px -18px 12px}"
        ".top .brand em{display:none}"
        ".top nav a{padding:5px 9px;font-size:12px}"
        ".top .modebadge{font-size:10px;padding:2px 7px}"
        ".top .modebadge:last-of-type{display:none}"   # secondary note is redundant on mobile
        "}</style>"
    )
    nav = (
        '<header class="top"><div class="brand">QX<em>trading workspace</em></div>'
        '<nav id="nav"><a href="/scanner">Discover</a><a href="/ideas">Trade Ideas</a>'
        '<a href="/trade">Trade Workspace</a><a href="/context">Context</a>'
        '<a href="/reports" class="on">Reports</a><a href="/settings">Settings</a></nav><div class="spacer"></div>'
        # Exchange clock + the universal safety label, matching every other page.
        # Reports previously carried only its own "read-only" badge, so the
        # LIVE EXECUTION DISABLED notice did not cover this route.
        '<span class="mut" id="clock" style="font-size:11.5px"></span>'
        '<span class="modebadge">LIVE EXECUTION DISABLED &middot; SIMULATED ONLY</span>'
        '<span class="modebadge" style="background:rgba(139,149,174,.14);color:#8b95ae;margin-left:6px">'
        'READ-ONLY &middot; ACCOUNTS KEPT SEPARATE</span></header>'
        '<script>(function(){var el=document.getElementById("clock");if(!el)return;'
        'function tick(){var s=document.getElementById("clock");if(!s)return;'
        'var d=new Date();'
        'var f=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour12:false,'
        'hour:"2-digit",minute:"2-digit",second:"2-digit"});'
        'var p=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",weekday:"short",'
        'hour:"2-digit",minute:"2-digit",hour12:false}).formatToParts(d);'
        'function g(t){for(var i=0;i<p.length;i++){if(p[i].type===t)return p[i].value}return ""}'
        'var wd=g("weekday"),hh=Number(g("hour"))%24,mm=Number(g("minute"));var st="CLOSED";'
        'if(wd==="Sat"||wd==="Sun")st="CLOSED_WEEKEND";'
        'else{var m=hh*60+mm;st=m<570?"PRE_MARKET":m<960?"REGULAR":m<1200?"AFTER_HOURS":"CLOSED"}'
        'var tone=st==="REGULAR"?"#26c281":(st==="PRE_MARKET"||st==="AFTER_HOURS")?"#e0a83c":"#8b95ae";'
        's.innerHTML=f.format(d)+" ET <span style=\\"color:"+tone+"\\">&middot; "+'
        'st.replace("_"," ").toLowerCase()+"</span>";}tick();setInterval(tick,1000);})();</script>'
    )
    html = DASHBOARD_HTML
    if nav not in html:
        # The dashboard wraps its content in .wrap; put the nav just inside <body>.
        if "<body>" in html:
            html = html.replace("<body>", "<body>" + nav, 1)
        else:
            html = nav + html
    if extra_css not in html and "</head>" in html:
        html = html.replace("</head>", extra_css + "</head>", 1)
    return html


# --------------------------------------------------------------------------- #
# PAGE — Context (levels / futures / dealer gamma)
# --------------------------------------------------------------------------- #

CONTEXT_BODY = """
<div class="row" style="justify-content:space-between">
  <h1 style="font-size:17px;margin:0">Context <span class="mut" style="font-size:12px" id="ctxstamp"></span></h1>
  <div class="row">
    <select id="csym">
      <optgroup label="ETF">
        <option selected>SPY</option><option>QQQ</option><option>IWM</option><option>GLD</option>
      </optgroup>
      <optgroup label="Index">
        <option>$SPX</option><option>$NDX</option><option>$RUT</option><option>$VIX</option>
      </optgroup>
      <optgroup label="Futures">
        <option>/ES</option><option>/NQ</option><option>/YM</option><option>/RTY</option>
        <option>/CL</option><option>/GC</option><option>/BTC</option>
      </optgroup>
    </select>
    <button onclick="loadAll()">Refresh</button>
    <button class="ghost" onclick="loadGamma()">Refresh gamma</button>
  </div>
</div>
<div id="warn"></div>
<div class="card"><h2>Levels <span class="mut" id="lvsrc"></span></h2><div id="lv"><span class="mut">Loading…</span></div></div>
<div class="two">
  <div class="card"><h2>Index futures &amp; basis</h2><div id="fut"><span class="mut">Loading…</span></div></div>
  <div class="card"><h2>Dealer gamma (GEX) <span class="mut" id="gxmeta"></span></h2><div id="gx"><span class="mut">Loading…</span></div></div>
</div>
<div class="card"><h2>Gamma by strike <span class="mut">net dealer gamma · calls positive · puts negative</span></h2><div id="gxprofile"><span class="mut">Loading…</span></div></div>
<script>
""" + HELPERS + """
let LV=null, GX=null;
function row(label,value,klass){return '<div class="kv" style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line);padding:4px 0"><span class="mut">'+esc(label)+'</span><b class="'+(klass||'')+'">'+value+'</b></div>'}
function loadLevels(){
  const sym=$('#csym').value;
  $('#lv').innerHTML='<span class="mut">Loading levels…</span>';
  j('/api/context/levels?symbol='+encodeURIComponent(sym)).then(function(d){
    LV=d;
    if(d.error){$('#lv').innerHTML='<div class="banner err">'+esc(d.error)+'</div>';return}
    $('#lvsrc').textContent=d.source+' · '+(d.quote_source||'')+(d.realtime?' · realtime':'')+' · '+exStamp(d.as_of);
    const p=d.prior_day||{},t=d.today||{},b=d.vwap_bands_20d||{};
    let h='<div class="kpis" style="margin-bottom:10px">'
      +kpi('Price',num(d.price,2),(d.change_pct==null?'':pctS(d.change_pct))+' today',cls(d.change_pct))
      +kpi('Prior close',num(p.close,2),'yesterday',cls(d.position_vs?d.position_vs.vs_prior_close:null))
      +kpi('Prior high',num(p.high,2),'resistance ref')
      +kpi('Prior low',num(p.low,2),'support ref')
      +kpi('ATR (14)',num(d.atr_14,2),'daily range')
      +kpi('20d VWAP',num(b.vwap,2),'anchored')+'</div>';
    h+='<div class="two"><div>'
      +row('Today open',num(t.open,2))+row('Today high',num(t.high,2))+row('Today low',num(t.low,2))
      +row('20-day high',num((d.range_20d||{}).high,2))+row('20-day low',num((d.range_20d||{}).low,2))
      +'</div><div>'
      +row('VWAP +2\u03c3',num(b.upper_2,2),'up')+row('VWAP +1\u03c3',num(b.upper_1,2),'up')
      +row('VWAP -1\u03c3',num(b.lower_1,2),'dn')+row('VWAP -2\u03c3',num(b.lower_2,2),'dn')
      +row('52-week high',num((d.fifty_two_week||{}).high,2))+row('52-week low',num((d.fifty_two_week||{}).low,2))
      +'</div></div>';
    const pv=d.position_vs||{};
    h+='<div class="mut" style="margin-top:9px;font-size:12px">Position vs: prior close '+pctS(pv.vs_prior_close)
      +' · prior high '+pctS(pv.vs_prior_high)+' · prior low '+pctS(pv.vs_prior_low)+' · 20d VWAP '+pctS(pv.vs_vwap)+'</div>';
    $('#lv').innerHTML=h;
  }).catch(function(e){$('#lv').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'});
}
function loadFutures(){
  $('#fut').innerHTML='<span class="mut">Loading futures…</span>';
  j('/api/context/futures').then(function(d){
    $('#fut').innerHTML=table(
      [{h:'Contract',f:r=>'<b>'+esc(r.symbol)+'</b> <span class="mut">'+esc(r.resolved||'')+'</span>'},
       {h:'Last',num:1,f:r=>num(r.last,2)},
       {h:'Chg',num:1,f:r=>'<span class="'+cls(r.change_pct)+'">'+pctS(r.change_pct)+'</span>'},
       {h:'Cash',f:r=>r.cash_symbol?(esc(r.cash_symbol)+' '+num(r.cash_last,2)):'<span class="mut">none declared</span>'},
       {h:'Basis',num:1,f:r=>r.basis_available===false?'<span class="mut">n/a</span>':'<span class="'+cls(r.basis_vs_cash)+'">'+num(r.basis_vs_cash,2)+'</span>'},
       {h:'Basis %',num:1,f:r=>r.basis_pct==null?'<span class="mut">n/a</span>':num(r.basis_pct,3)+'%'},
       {h:'Prior H/L',f:r=>num(r.prior_high,2)+' / '+num(r.prior_low,2)},
       {h:'Src',f:r=>'<span class="mut">'+esc(r.source||'')+'</span>'}],d.futures,'No futures data.');
  }).catch(function(e){$('#fut').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'});
}
function loadGamma(){
  const sym=$('#csym').value;
  $('#gx').innerHTML='<span class="mut">Loading option chain…</span>';
  $('#gxprofile').innerHTML='<span class="mut">Loading…</span>';
  j('/api/context/gamma?symbol='+encodeURIComponent(sym)).then(function(d){
    GX=d;
    if(d.error){$('#gx').innerHTML='<div class="banner err">'+esc(d.error)+'</div>';$('#gxprofile').innerHTML='';return}
    const ch=d.chain||{};
    $('#gxmeta').textContent=(ch.contracts||0)+' contracts · '+(ch.expiries||[]).length+' expiries · '
      +(ch.is_delayed?'DELAYED':'not delayed')+(ch.is_truncated?' · TRUNCATED':'');
    const short=d.net_gamma<0;
    let h='<div class="kpis" style="margin-bottom:10px">'
      +kpi('Net gamma',(d.net_gamma/1e9).toFixed(2)+'B',short?'dealers short gamma':'dealers long gamma',short?'dn':'up')
      +kpi('Gamma flip',num(d.gamma_flip_price,2),'regime pivot')
      +kpi('Call wall',num(d.call_wall,2),'resistance')
      +kpi('Put wall',num(d.put_wall,2),'support')+'</div>';
    h+=row('Regime',esc(d.regime),short?'dn':'up')
      +row('Call / put gamma ratio',num(d.call_put_gamma_ratio,2))
      +row('0DTE volume share',pct(d.zero_dte_volume_ratio))
      +row('Expected move 1\u03c3',num(d.expected_move_1sigma,2))
      +row('Expected move 2\u03c3',num(d.expected_move_2sigma,2))
      +row('Spot',num(d.spot,2))
      +row('Settlement provenance',esc(d.settlement_source)+' / '+esc(d.settlement_confidence),
           d.settlement_confidence==='VERIFIED'?'up':'warn');
    $('#gx').innerHTML=h;
    const prof=(d.profile||[]).filter(function(r){return r.call_oi||r.put_oi});
    if(!prof.length){$('#gxprofile').innerHTML='<span class="mut">No strike profile with open interest.</span>';return}
    const maxAbs=Math.max.apply(null,prof.map(function(r){return Math.abs(r.gex)}).concat([1]));
    const near=prof.slice().sort(function(a,b){return Math.abs(a.strike-d.spot)-Math.abs(b.strike-d.spot)}).slice(0,30)
      .sort(function(a,b){return b.strike-a.strike});
    $('#gxprofile').innerHTML='<div class="row" style="justify-content:space-between;margin-bottom:6px">'
      +'<span class="mut" style="font-size:12px">30 strikes nearest spot of '+prof.length+' with open interest</span>'
      +'<span class="mut" style="font-size:12px">max |GEX| '+(maxAbs/1e6).toFixed(1)+'M</span></div>'
      +'<div class="scroll" style="max-height:320px">'+table(
      [{h:'Strike',f:r=>'<b>'+num(r.strike,2)+'</b>'},
       {h:'Net GEX',num:1,f:r=>'<span class="'+cls(r.gex)+'">'+(r.gex/1e6).toFixed(2)+'M</span>'},
       {h:'Bar',f:r=>bar(r.gex,maxAbs)},
       {h:'Call OI',num:1,f:r=>num(r.call_oi,0)},
       {h:'Put OI',num:1,f:r=>num(r.put_oi,0)},
       {h:'vs spot',num:1,f:r=>{const p=((r.strike/d.spot-1)*100);return '<span class="mut">'+p.toFixed(2)+'%</span>'}}],
      near,'—')+'</div>';
  }).catch(function(e){$('#gx').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'});
}
function loadAll(){loadLevels();loadFutures();loadGamma()}
$('#csym').addEventListener('change',loadAll);
loadAll();
</script>
"""


# --------------------------------------------------------------------------- #
# PAGE — Settings (Schwab credentials & connection, secrets masked)
# --------------------------------------------------------------------------- #

SETTINGS_BODY = """
<h1 style="font-size:17px;margin:0 0 4px">Settings</h1>
<div class="mut" style="font-size:12.5px;margin-bottom:10px">Schwab connection and credentials. Read-only view — secrets are never shown.</div>
<div id="warn"></div>
<div class="card"><h2>Credentials <span class="mut" id="ststamp"></span></h2><div id="creds"><span class="mut">Loading…</span></div></div>
<div class="two">
  <div class="card"><h2>OAuth token state</h2><div id="tok"><span class="mut">Loading…</span></div></div>
  <div class="card"><h2>Provider health</h2><div id="hlth"><span class="mut">Probing…</span></div></div>
</div>
<div class="card"><h2>Notes</h2><div id="notes" class="mut" style="font-size:12px"></div></div>
<script>
""" + HELPERS + """
function row(label,value,klass){return '<div class="kv" style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line);padding:4px 0"><span class="mut">'+esc(label)+'</span><b class="'+(klass||'')+'">'+value+'</b></div>'}
function yn(v){return v?'<span class="up">yes</span>':'<span class="dn">no</span>'}
async function loadSettings(){
  try{
    const d=await j('/api/settings/schwab');
    $('#ststamp').textContent=exStamp(d.as_of);
    if(d.error){$('#creds').innerHTML='<div class="banner err">'+esc(d.error)+'</div>';return}
    const c=d.client||{},t=d.token||{},h=d.health||{};
    $('#creds').innerHTML='<div class="kpis" style="margin-bottom:10px">'
      +kpi('Client ID',c.client_id_present?'present':'missing',esc(c.client_id_masked||''),c.client_id_present?'up':'dn')
      +kpi('Client secret',c.client_secret_present?'present':'missing','never displayed',c.client_secret_present?'up':'dn')
      +kpi('Redirect URI',esc(c.redirect_uri||'—'),'must match the Schwab app')
      +kpi('.env file',d.env_exists?'found':'missing',esc(d.env_path||''),d.env_exists?'up':'warn')+'</div>'
      +row('Auth base URL','<span class="mut">'+esc(c.auth_base_url||'')+'</span>')
      +row('API base URL','<span class="mut">'+esc(c.api_base_url||'')+'</span>')
      +row('Token path','<span class="mut">'+esc(c.token_path||'')+'</span>')
      +row('Token file on disk',d.token_file_exists?yn(true):yn(false));
    $('#tok').innerHTML=row('Configured',yn(t.configured))
      +row('Token present',yn(t.has_token))
      +row('Access token valid',yn(t.access_token_valid))
      +row('Refresh token valid',yn(t.refresh_token_valid))
      +row('Restart required',t.restart_required?'<span class="warn">yes</span>':'no')
      +row('Message','<span class="mut">'+esc(t.message||'')+'</span>')
      +(d.authorization_url?'<div style="margin-top:9px"><div class="mut" style="font-size:11.5px;margin-bottom:4px">1 · Open this URL and approve access at Schwab</div>'
        +'<div class="scroll" style="max-height:110px"><code id="authurl" style="font-size:11px;word-break:break-all">'+esc(d.authorization_url)+'</code></div>'
        +'<div class="row" style="margin-top:7px"><button onclick="openAuth()">Open in a new tab</button>'
        +'<button class="ghost" onclick="copyAuth()">Copy URL</button></div>'
        +'<div style="margin-top:11px"><div class="mut" style="font-size:11.5px;margin-bottom:4px">2 · Paste the redirect URL back here</div>'
        +'<div class="mut" style="font-size:11.5px;margin-bottom:5px">Schwab sends you to '
        +'<code style="font-size:11px">'+esc(c.redirect_uri||'https://127.0.0.1')+'</code> and the page will fail to load — that is expected. '
        +'Copy the <b>entire address bar</b> (it contains <code style="font-size:11px">code=…</code>) and paste it below.</div>'
        +'<textarea id="authcb" rows="3" placeholder="https://127.0.0.1/?code=...&amp;session=..." '
        +'style="width:100%;box-sizing:border-box;font-family:monospace;font-size:11px;background:#0d1420;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:7px"></textarea>'
        +'<div class="row" style="margin-top:7px"><button onclick="submitAuth()">Complete authorization</button>'
        +'<span class="mut" style="font-size:11.5px">saved server-side to '+esc(c.token_path||'data/secrets/schwab_token.json')+' — you do not keep it</span></div>'
        +'<div id="authmsg" style="margin-top:7px"></div></div></div>':'');
    $('#hlth').innerHTML=row('Market data probe',h.ok?'<span class="up">ok</span>':'<span class="dn">failed</span>')
      +row('Endpoint','<span class="mut">'+esc(h.probe||'')+'</span>')
      +(h.ok?(row('SPY last',num(h.last,2))+row('Realtime',yn(h.realtime))+row('Resolved',esc(h.resolved_symbol||'')))
            :row('Error','<span class="dn">'+esc(h.error||'')+'</span>'));
    const ah=await j('/api/settings/schwab/accounts').catch(function(){return null});
    if(ah){$('#hlth').innerHTML+=row('Trader probe',ah.ok?'<span class="up">ok</span>':'<span class="dn">failed</span>')
      +row('Accounts','<span class="mut">'+esc((ah.accounts||[]).map(function(a){return (a.type||'')+' '+a.masked}).join(', ')||ah.error||'—')+'</span>')}
    $('#notes').innerHTML=(d.notes||[]).map(function(n){return '<div style="padding:3px 0">'+esc(n)+'</div>'}).join('');
  }catch(e){$('#creds').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
function copyAuth(){
  const code=document.querySelector('#authurl')||document.querySelector('#tok code');
  if(!code)return;
  navigator.clipboard.writeText(code.textContent).then(function(){alert('Authorization URL copied.')},
    function(){alert('Copy failed — select the text manually.')});
}
function openAuth(){
  const code=document.querySelector('#authurl')||document.querySelector('#tok code');
  const url=code&&code.textContent?code.textContent.trim():'';
  if(!url){alert('No authorization URL available yet.');return}
  window.open(url,'_blank','noopener');
}
async function submitAuth(){
  const el=document.getElementById('authcb');
  const msg=document.getElementById('authmsg');
  const value=(el&&el.value||'').trim();
  if(!value){ if(msg)msg.innerHTML='<div class="banner err">Paste the full callback URL first.</div>'; return; }
  if(msg)msg.innerHTML='<span class="mut">Exchanging the code with Schwab…</span>';
  try{
    const r=await fetch('/api/settings/schwab/authorize',{
      method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({callback:value})});
    let d={};
    try{ d=await r.json(); }catch(e){ d={ok:false,error:'unreadable response'}; }
    if(d.ok){
      if(msg)msg.innerHTML='<div class="banner info"><b>Authorized.</b> Token saved to <code>'
        +esc(d.token_path||'')+'</code>. Reloading status…</div>';
      if(el)el.value='';
      setTimeout(loadSettings,1000);
    } else {
      if(msg)msg.innerHTML='<div class="banner err">'+esc(d.error||'Authorization failed')+'</div>';
    }
  }catch(e){
    if(msg)msg.innerHTML='<div class="banner err">'+esc(e.message)+'</div>';
  }
}
loadSettings();
</script>
"""


# --------------------------------------------------------------------------- #
# Sector & Industry Explorer (injected into the Discover page)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# PAGE — Trade Ideas (aggregate candidate set across the scanned universe)
# --------------------------------------------------------------------------- #

IDEAS_BODY = """
<div class="row" style="justify-content:space-between">
  <h1 style="font-size:17px;margin:0">Trade Ideas <span class="mut" style="font-size:12px" id="idstamp"></span></h1>
  <div class="row">
    <select id="idsort"></select>
    <select id="idsector"><option value="">All sectors</option></select>
    <button onclick="loadIdeas()">Refresh</button>
    <button class="ghost" onclick="rebuild()">Rebuild snapshot</button>
  </div>
</div>
<div id="idwarn"></div>
<div class="card"><h2>Views <span class="mut">one shared candidate set — these are filters, not separate scanners</span></h2>
  <div class="row" id="idviews"></div>
  <div class="mut" style="margin-top:7px;font-size:11.5px" id="idnote"></div>
</div>
<div class="grid2">
  <div class="card"><h2 id="idlisthead">Ideas</h2><div class="scroll" style="max-height:560px" id="idlist"></div></div>
  <div class="card"><h2>Selected idea <span class="mut" id="idsym">none</span></h2><div id="iddetail">
    <span class="mut">Select an idea to see why it is here, what must happen before entry, and what invalidates it.</span>
  </div></div>
</div>
<script>
""" + HELPERS + """
let ID=null, IDROW=null, IDVIEW='ready_now', IDSORT='entry_readiness', IDSECTOR='';
function rsCell(v){ if(v==null) return '<span class="mut">—</span>'; return '<span class="'+cls(v)+'">'+(v>0?'+':'')+num(v,2)+'%</span>' }
async function loadIdeas(){
  $('#idlist').innerHTML=spinner('Reading the candidate snapshot…');
  try{
    ID=await j('/api/ideas?view='+encodeURIComponent(IDVIEW)+'&sort='+encodeURIComponent(IDSORT)
      +'&limit=300'+(IDSECTOR?'&sector='+encodeURIComponent(IDSECTOR):''));
    renderIdeas();
  }catch(e){$('#idlist').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
function renderIdeas(){
  const d=ID;
  $('#idstamp').textContent=d.has_snapshot
    ? (d.ideas.length+' of '+d.row_count+' candidates · snapshot '+Math.round((d.age_seconds||0)/60)+' min old')
    : 'no snapshot';
  $('#idsort').innerHTML=(d.sorts||[]).map(function(s){
    return '<option value="'+esc(s.id)+'"'+(s.id===IDSORT?' selected':'')+' title="'+esc(s.description)+'">Sort: '+esc(s.label)+'</option>'}).join('');
  $('#idviews').innerHTML=(d.views||[]).map(function(v){
    return '<button class="'+(v.id===IDVIEW?'':'ghost')+'" title="'+esc(v.description)+'" onclick="setView(&quot;'+esc(v.id)+'&quot;)">'
      +esc(v.label)+' <span class="mut">('+v.count+')</span></button>'}).join('');
  let warn='';
  if(!d.has_snapshot) warn='<div class="banner">No candidate snapshot exists yet. Click <b>Rebuild snapshot</b> to scan the universe. This takes a few minutes because bars are fetched per member.</div>';
  else if(d.stale) warn='<div class="banner err"><b>SNAPSHOT STALE</b> — '+Math.round((d.age_seconds||0)/60)+' min old (TTL '+6+'h). Current-readiness views are '
    +'<b>emptied</b>: a stale latch is not an actionable idea. Use <b>Rebuild snapshot</b>, or read these rows as history only.</div>';
  if(d.building&&d.building.running) warn+='<div class="banner info">Building: '+esc(d.building.current||'')+' ('+d.building.done+'/'+d.building.total+')</div>';
  (d.errors||[]).slice(0,3).forEach(function(e){warn+='<div class="banner err">'+esc(e)+'</div>'});
  $('#idwarn').innerHTML=warn;
  $('#idnote').innerHTML=d.has_snapshot
    ? ('Scanned '+d.sectors_scanned+' ETFs · universe '+d.universe+' · rules '+((d.rules||{}).momo_trend||'')
       +' / '+((d.rules||{}).phases||'')+' / '+((d.rules||{}).entry||'')
       +(IDVIEW==='pullback_watch'?'<br><b>Pullback definition:</b> Boyd phase 4 (uptrend losing Hull momentum), or Trend UP with Momo not yet UP — never bearish or structurally broken.':'')
       +(d.stale?'<br><span class="dn">Snapshot is stale: current-readiness views are gated off.</span>':''))
    : '';
  const v=(d.views||[]).find(function(x){return x.id===IDVIEW});
  $('#idlisthead').innerHTML='Ideas <span class="mut">'+esc(v?v.label:IDVIEW)+' · showing '+d.shown+(d.message?'':' of '+d.row_count)+'</span>';
  if(!d.ideas.length){
    $('#idlist').innerHTML='<div class="banner">'+esc(d.message||'NOTHING_QUALIFIES — no ideas are manufactured to fill this page.')+'</div>';
    return;
  }
  // Short ideas carry a measured negative expectancy; say so above the table
  // rather than letting a SHORT chip read as an equal-status recommendation.
  const shortCount=d.ideas.filter(function(r){return r.direction==='SHORT'}).length;
  const shortNote=shortCount?('<div class="banner" style="margin-bottom:8px">'
    +'<b>'+shortCount+' of '+d.ideas.length+' rows are SHORT — unproven.</b> Short signals measured '
    +'<b>-0.60 R</b> per trade (PF 0.53) over a 2-year backtest, against <b>+0.41 R</b> (PF 1.37) for LONG. '
    +'The logic is symmetric with the long side, so this is market drift rather than a bug; a regime gate that '
    +'allowed shorts only in falling markets was tested and made results worse. Informational, not tradeable.</div>'):'';
  $('#idlist').innerHTML=shortNote+table(
    [{h:'Symbol',f:r=>'<b>'+esc(r.symbol)+'</b>'},
     {h:'Sector',f:r=>'<span class="mut">'+esc(r.sector_symbol)+'</span>'},
     {h:'Dir',f:r=>'<span class="chip '+esc(r.direction)+'">'+esc(r.direction)+'</span>'},
     {h:'Entry state',f:r=>'<span class="chip">'+esc(r.entry_state)+'</span>'},
     {h:'Horizon',f:r=>'<span class="mut">'+esc(r.horizon)+'</span>'},
     {h:'Phase',num:1,f:r=>r.phase==null?'—':(String(r.phase)+(r.is_pullback?' ⚠':''))},
     {h:'Fresh',f:r=>freshChip(r.freshness)},
     {h:'Trigger',num:1,f:r=>num(r.trigger,2)},
     {h:'Ref stop',num:1,f:r=>num(r.invalidation,2)},
     {h:'R:R plan',num:1,f:r=>num(r.reward_risk,2)},
     {h:'RS/parent',num:1,f:r=>rsCell(r.rs_vs_parent)},
     {h:'RS/mkt',num:1,f:r=>rsCell(r.rs_vs_market)},
     {h:'',f:r=>'<button class="ghost" onclick="pickIdea(&quot;'+esc(r.symbol)+'&quot;)">Why?</button>'}],
    d.ideas,'Nothing qualifies in this view.');
}
function setView(v){IDVIEW=v;loadIdeas()}
function pickIdea(sym){
  const r=(ID.ideas||[]).find(function(x){return x.symbol===sym}); if(!r)return;
  IDROW=r;
  $('#idsym').textContent=sym;
  let h='<div class="row" style="justify-content:space-between"><div><b style="font-size:15px">'+esc(r.symbol)+'</b> '
   +'<span class="mut">'+esc(r.company||'')+' · '+esc(r.sector_name||'')+'</span></div>'
   +'<span class="chip '+esc(r.direction)+'">'+esc(r.direction)+'</span></div>';
  h+='<div class="kpis" style="margin:8px 0">'
   +kpi('Entry state',esc(r.entry_state||'—'),esc(r.horizon||''))
   +kpi('Trigger',num(r.trigger,2),esc(r.playbook||''))
   +kpi('Ref. stop',num(r.invalidation,2),'REFERENCE — not enforced','dn')
   +kpi('Target',num(r.target,2),'R:R plan '+num(r.reward_risk,2)+' — configured, not realised','up')
   +kpi('Chase limit',num(r.chase_limit,2),r.extended?'EXTENDED':'inside limit',r.extended?'dn':'')
   +kpi('RVol',num(r.rvol,2),'relative volume')+'</div>';
  h+='<div class="two"><div>'+table([{h:'Answer',f:x=>esc(x.k)},{h:'',f:x=>x.v}], [
      {k:'Why this stock?', v:esc((r.momentum||'')+' momentum, '+(r.trend||'')+' trend · phase '+String(r.phase==null?'—':r.phase))},
      {k:'Why this playbook?', v:esc(r.playbook||'no playbook — alignment only')},
      {k:'Why now?', v:esc(r.entry_reason||'—')},
      {k:'Before entry?', v:esc(r.trigger==null?'no trigger defined':'price through '+num(r.trigger,2)+' with a confirming candle')},
      {k:'What invalidates?', v:esc(r.invalidation==null?'no reference level computed'
        :'reference level '+num(r.invalidation,2)+' — the study does NOT exit here')},
      {k:'Nearby limit?', v:esc('target '+num(r.target,2)+' at '+num(r.reward_risk,2)+'R')},
      {k:'Conflicts?', v:esc(conflicts(r))},
      {k:'Duplicate exposure?', v:'<span class="mut">'+esc(r.also_in&&r.also_in.length?('also held by '+r.also_in.join(', ')):'not in another scanned ETF')+'</span>'},
      {k:'Data', v:'<span class="mut">'+esc('observed '+(r.observed_at?exStamp(r.observed_at):'time unavailable')+' · bar '+exDate(r.bar_date)+' · weight '+(r.weight==null?'n/a':(r.weight*100).toFixed(2)+'%'))+'</span>'},
      {k:'Next action', v:esc(nextAction(r))}])+'</div></div>';
  h+='<div class="row" style="margin-top:9px"><button onclick="openIdeaTrade()">Open Trade Workspace →</button>'
   +'<button class="ghost" onclick="whyRanked()">Why ranked here?</button>'
   +'<span class="chip">'+esc(r.instrument_evaluation||'UNDERLYING_ONLY')+'</span></div>'
   +'<div id="idwhy" style="margin-top:8px"></div>';
  $('#iddetail').innerHTML=h;
}
function conflicts(r){
  const c=[];
  if(r.rs_parent!=null && r.rs_parent<0) c.push('lagging its own sector ETF');
  if(r.rs_market!=null && r.rs_market<0) c.push('lagging the market');
  if(r.rvol!=null && r.rvol<1) c.push('below-average relative volume');
  if(r.extended) c.push('already beyond the chase limit');
  return c.length?c.join('; '):'none identified from stored evidence';
}
function nextAction(r){
  if(r.entry_state==='TRIGGER_CONFIRMED') return 'a live plan exists; manage it, or wait for a fresh signal';
  if(r.entry_state==='BREAKOUT_WATCH') return 'wait for the entry candle through '+num(r.trigger,2)+' with volume';
  if(r.entry_state==='PULLBACK_CANDIDATE') return 'wait for a pullback that holds, then a fresh break of the trigger';
  if(r.entry_state==='EXTENDED_WAIT') return 'wait for price back inside the chase limit';
  return 'no action until a valid structure forms';
}
async function whyRanked(){
  const box=$('#idwhy'); if(!IDROW)return;
  box.innerHTML=spinner('Explaining the ranking…');
  try{
    const d=await j('/api/ideas/why?symbol='+encodeURIComponent(IDROW.symbol)+'&view='+encodeURIComponent(IDVIEW)+'&sort='+encodeURIComponent(IDSORT));
    if(!d.ok){box.innerHTML='<div class="banner err">'+esc(d.error)+'</div>';return}
    box.innerHTML='<div class="banner info"><b>'+esc(d.symbol)+'</b> is #'+d.position+' of '+d.of+' in this view</div>'
      +'<ul style="margin:6px 0 0 18px;padding:0">'+(d.reasons||[]).map(function(x){return '<li style="margin:3px 0">'+esc(x)+'</li>'}).join('')+'</ul>'
      +'<div class="mut" style="margin-top:6px;font-size:11.5px">'+esc(d.note)+'</div>';
  }catch(e){box.innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
function openIdeaTrade(){
  const r=IDROW; if(!r)return;
  const snap={setup_id:r.symbol+'-'+r.horizon+'-'+r.sector_symbol, setup_version:1, symbol:r.symbol,
    side:r.direction==='SHORT'?'SHORT':'LONG', score:null,
    signal:(r.momentum||'')+' / '+(r.trend||''), entry:r.trigger||r.price,
    invalidation:r.invalidation, target:r.target, risk_reward:r.reward_risk, factors:{},
    timeframe:'1d', rule_version:r.rule_version, sector_parent:r.sector_symbol,
    sector_universe:r.universe, entry_state:r.entry_state, playbook:r.playbook,
    publication_state:'RESEARCH_ONLY', executable:false, captured_at:new Date().toISOString()};
  try{localStorage.setItem('qx.selectedSetup',JSON.stringify(snap))}catch(e){}
  location.href='/trade';
}
async function rebuild(){
  try{
    const r=await j('/api/ideas/build',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({force:false})});
    $('#idwarn').innerHTML='<div class="banner info">'+(r.ok?'Snapshot build started in the background. This page will show progress on refresh.':'Build not started: '+esc(r.error||''))+'</div>';
  }catch(e){$('#idwarn').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
$('#idsort').addEventListener('change',function(){IDSORT=this.value;loadIdeas()});
$('#idsector').addEventListener('change',function(){IDSECTOR=this.value;loadIdeas()});
(async function(){
  try{
    const c=await j('/api/explorer/catalog');
    $('#idsector').innerHTML='<option value="">All sectors</option>'
      +c.sectors.concat(c.industries).map(function(x){return '<option value="'+esc(x.symbol)+'">'+esc(x.symbol+' · '+x.name)+'</option>'}).join('');
  }catch(e){}
  loadIdeas();
})();
</script>
"""
# --------------------------------------------------------------------------- #
# Sector & Industry Explorer (injected into the Discover page)
# --------------------------------------------------------------------------- #

EXPLORER_SECTION = """
<div class="card"><h2>Sector &amp; industry explorer
  <span class="mut" id="exstamp">click any row to explore its stocks</span></h2>
  <div class="row" style="margin-bottom:8px">
    <select id="exuniverse"></select>
    <select id="extf"><option value="1d" selected>Swing (daily)</option><option value="15m">Intraday (15m)</option></select>
    <span class="mut" style="font-size:11.5px">The two universes are never substituted for one another.</span>
  </div>
  <div id="excatalog"><span class="mut">Loading sectors…</span></div>
</div>
<div id="exdetail"></div>
"""

EXPLORER_JS = """
let CAT=null, EX=null, EXROW=null, EXVIEW='aligned_up';
function spinner(msg){return '<span class="mut">'+esc(msg||'Loading…')+'</span>'}
function rsCell(v){ if(v==null) return '<span class="mut">—</span>';
  return '<span class="'+cls(v)+'">'+(v>0?'+':'')+num(v,2)+'%</span>'; }
function viewLabel(id){const v=(EX&&EX.views||[]).find(function(x){return x.id===id});return v?v.label:id}
async function loadCatalog(){
  try{
    CAT=await j('/api/explorer/catalog');
    $('#exuniverse').innerHTML=(CAT.universes||[]).map(function(u){
      return '<option value="'+esc(u.id)+'">'+esc(u.label)+' — '+esc(u.description)+'</option>'}).join('');
    const cols=[{h:'ETF',f:r=>'<b>'+esc(r.symbol)+'</b>'},{h:'Name',f:r=>esc(r.name)},
      {h:'Kind',f:r=>'<span class="chip">'+esc(r.kind)+'</span>'},
      {h:'Parent',f:r=>esc(r.parent||'—')},
      {h:'',f:r=>'<button class="ghost" onclick="exploreSector(&quot;'+esc(r.symbol)+'&quot;)">Explore →</button>'}];
    const secs=CAT.sectors||[], inds=CAT.industries||[];
    const head=function(t,n){return '<div class="mut" style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">'+t+' ('+n+')</div>'};
    $('#excatalog').innerHTML='<div class="two"><div>'+head('Sectors',secs.length)+table(cols,secs,'none')+'</div>'
      +'<div>'+head('Industries',inds.length)+table(cols,inds,'none')+'</div></div>';
  }catch(e){$('#excatalog').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
async function exploreSector(sym,view){
  if(view) EXVIEW=view;
  $('#exdetail').innerHTML='<div class="card">'+spinner('Exploring '+sym+' — fetching constituents and studies…')+'</div>';
  $('#exstamp').textContent='exploring '+sym+'…';
  try{
    const u=$('#exuniverse').value, tf=$('#extf').value;
    EX=await j('/api/explorer/sector?symbol='+encodeURIComponent(sym)+'&universe='+encodeURIComponent(u)
      +'&timeframe='+encodeURIComponent(tf)+'&view='+encodeURIComponent(EXVIEW)+'&limit=200');
    renderExplorer(); EXROW=null;
  }catch(e){$('#exdetail').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
function renderExplorer(){
  const d=EX, b=d.breadth||{}, m=d.membership||{}, p=d.parent||{};
  $('#exstamp').textContent=d.symbol+' · '+d.row_count+' members · '+exStamp(d.generated_at);
  let h='<div class="card"><div class="row" style="justify-content:space-between"><div>'
   +'<b style="font-size:16px">'+esc(d.symbol)+'</b> '
   +'<span class="chip '+(p.aligned_up?'LONG':'WAIT')+'">Momo '+(p.momentum||'—')+' / Trend '+(p.trend||'—')+'</span> '
   +'<span class="mut">'+esc(p.phase_label||'')+'</span></div>'
   +'<button class="ghost" onclick="exploreSector(&quot;'+esc(d.symbol)+'&quot;)">Refresh</button></div>';
  h+='<div class="kpis" style="margin-top:9px">'
   +kpi('Parent price',num(p.price,2),pctS(p.change_pct),cls(p.change_pct))
   +kpi('Members',String(d.row_count),d.membership_rows+' rows from source')
   +kpi('Trend up',pct(b.trend_up_pct),(b.covered||0)+' of '+(b.denominator||0)+' eligible')
   +kpi('Momo+Trend up',pct(b.aligned_pct),'the qualified set')
   +kpi('Weighted',b.holdings_weighted_aligned_pct==null?'—':pct(b.holdings_weighted_aligned_pct),'holdings-weighted')
   +kpi('Weight covered',b.weight_covered_pct==null?'—':num(b.weight_covered_pct,1)+'%','of fund weight')+'</div>';
  (d.warnings||[]).forEach(function(w){h+='<div class="banner">'+esc(w)+'</div>'});
  h+='<div class="mut" style="margin-top:7px;font-size:11.5px">Universe <b>'+esc(m.universe)+'</b> · '+esc(m.source||'')
   +' · <b>'+esc(m.coverage_label||'coverage unknown')+'</b>'
   +' · holdings as of '+esc(m.holdings_as_of||'unknown (retrieval time is not a holdings date)')
   +'<br>rules '+esc((d.rules||{}).momo_trend||'')+' / '+esc((d.rules||{}).phases||'')+' / '+esc((d.rules||{}).entry||'')+'</div>';
  h+='<div class="row" style="margin-top:9px">'+(d.views||[]).map(function(v){
    return '<button class="'+(v.id===EXVIEW?'':'ghost')+'" onclick="exploreSector(&quot;'+esc(d.symbol)+'&quot;,&quot;'+esc(v.id)+'&quot;)">'
      +esc(v.label)+' <span class="mut">('+v.count+')</span></button>'}).join('')+'</div>';
  h+='<div class="mut" style="margin-top:6px;font-size:11.5px">'+esc(b.denominator_note||'')+'</div></div>';
  h+='<div class="grid2"><div class="card"><h2>'+esc(viewLabel(EXVIEW))
   +' <span class="mut">showing '+d.shown+' of '+d.row_count+'</span></h2><div class="scroll" style="max-height:470px">'
   +table(
     [{h:'Symbol',f:r=>'<b>'+esc(r.symbol)+'</b>'+(r.error?' <span class="chip">no data</span>':'')},
      {h:'Company',f:r=>'<span class="mut">'+esc((r.company||'').slice(0,24))+'</span>'},
      {h:'Wt',num:1,f:r=>r.weight==null?'—':(r.weight*100).toFixed(2)+'%'},
      {h:'Price',num:1,f:r=>num(r.price,2)},
      {h:'Momo',f:r=>r.momentum?'<span class="chip '+esc(r.momentum)+'">'+esc(r.momentum)+'</span>':'<span class="mut">—</span>'},
      {h:'Trend',f:r=>r.trend?'<span class="chip '+esc(r.trend)+'">'+esc(r.trend)+'</span>':'<span class="mut">—</span>'},
      {h:'Bars',num:1,f:r=>r.bars_since_alignment==null?'—':num(r.bars_since_alignment,0)},
      {h:'Ph',num:1,f:r=>r.phase==null?'—':r.phase},
      {h:'RS/parent',num:1,f:r=>rsCell((r.rs_vs_parent||{})['20d'])},
      {h:'RS/mkt',num:1,f:r=>rsCell((r.rs_vs_market||{})['20d'])},
      {h:'Entry',f:r=>'<span class="chip">'+esc((r.entry||{}).state||'—')+'</span>'},
      {h:'Fresh',f:r=>freshChip(r.freshness)},
      {h:'',f:r=>'<button class="ghost" onclick="selectMember(&quot;'+esc(r.symbol)+'&quot;)">Detail</button>'}],
     d.rows,'No members in this view.')+'</div></div>'
   +'<div class="card"><h2>Selected stock <span class="mut" id="memsym">none</span></h2>'
   +'<div id="memdetail"><span class="mut">Select a member to see its plan and evidence-based notes.</span></div></div></div>';
  $('#exdetail').innerHTML=h;
}
function selectMember(symbol){
  const r=(EX.rows||[]).find(function(x){return x.symbol===symbol}); if(!r)return;
  EXROW=r;
  const e=r.entry||{};
  $('#memsym').textContent=symbol;
  let h='<div class="row" style="justify-content:space-between"><div><b style="font-size:15px">'+esc(r.symbol)+'</b> '
   +'<span class="mut">'+esc(r.company||'')+'</span></div><span class="chip">'+esc(e.state||'—')+'</span></div>';
  h+='<div class="kpis" style="margin:8px 0">'
   +kpi('Momo',esc(r.momentum||'—'),esc(r.trend||'')+' trend')
   +kpi('Phase',r.phase==null?'—':String(r.phase),esc((r.phase_label||'').slice(0,24)))
   +kpi('Trigger',num(e.trigger,2),esc(e.playbook||'no playbook'))
   +kpi('Ref. stop',num(e.invalidation,2),'REFERENCE — not enforced','dn')
   +kpi('Target',num(e.target,2),'R:R plan '+num(e.reward_risk,2)+' — configured, not realised','up')
   +kpi('Chase limit',num(e.chase_limit,2),r.extended?'EXTENDED':'inside limit',r.extended?'dn':'')
   +kpi('Freshness',esc((r.freshness||{}).overall||'—'),
        esc(((r.freshness||{}).quote||{}).age_seconds==null?'no observation time':num(((r.freshness||{}).quote||{}).age_seconds,1)+'s old'))+'</div>';
  // F23: state plainly what the study actually does on the way out, and whether the
  // reference level has already been breached. A displayed level that is never
  // enforced must not read as a protected stop.
  if(e.study_exit_rule){
    const breach=e.stop_breach||{};
    h+='<div class="banner info" style="margin-top:6px;font-size:11.5px"><b>Exit rule (study):</b> '
      +esc(e.study_exit_rule)
      +'<br><b>Reference level:</b> '+esc(e.risk_note||'')
      +(breach.evaluated?'<br><b>Recent price vs reference:</b> '+esc(breach.note||''):'')
      +'</div>';
  }
  h+='<div class="mut" style="font-size:12px">'+esc(e.reason||'')+'</div>';
  h+='<div class="mut" style="font-size:11.5px;margin-top:4px">observed '
   +esc(String(r.observed_at||'unknown').slice(0,19))+' · bar '+esc(String(r.bar_date||'undated').slice(0,10))
   +' · '+esc((r.freshness||{}).overall||'UNKNOWN')+'</div>';
  h+='<div style="margin-top:8px">'+table(
     [{h:'Relative to',f:x=>esc(x.k)},{h:'5d',num:1,f:x=>rsCell((x.r||{})['5d'])},
      {h:'20d',num:1,f:x=>rsCell((x.r||{})['20d'])},{h:'60d',num:1,f:x=>rsCell((x.r||{})['60d'])}],
     [{k:'Parent ETF',r:r.rs_vs_parent||{}},{k:'Market (SPY)',r:r.rs_vs_market||{}}])+'</div>';
  h+='<div class="row" style="margin-top:9px"><button onclick="openMemberTrade()">Open Trade Workspace →</button>'
   +'<button class="ghost" onclick="loadMemberNotes()">AI notes</button></div><div id="membnotes" style="margin-top:9px"></div>';
  $('#memdetail').innerHTML=h;
}
async function loadMemberNotes(){
  const box=$('#membnotes'); if(!EXROW)return;
  box.innerHTML=spinner('Building notes from stored evidence…');
  try{
    const d=await j('/api/explorer/notes',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({row:EXROW,sector:{timeframe:EX.timeframe,universe:EX.universe,rules:EX.rules},
        breadth:EX.breadth,parent:EX.parent})});
    box.innerHTML='<div class="mut" style="font-size:11.5px">notes '+esc(d.note_version)+' · '
      +esc(exStamp(d.generated_at))
      +(d.missing_inputs&&d.missing_inputs.length?' · missing: '+esc(d.missing_inputs.join(', ')):'')+'</div>'
      +'<ul style="margin:6px 0 0 18px;padding:0">'+(d.statements||[]).map(function(s){
        return '<li style="margin:3px 0">'+esc(s)+'</li>'}).join('')+'</ul>'
      +'<div class="mut" style="margin-top:6px;font-size:11.5px">This note cannot: '+esc((d.cannot||[]).join(', '))+'.</div>';
  }catch(e){box.innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
function openMemberTrade(){
  const r=EXROW; if(!r)return;
  const e=r.entry||{};
  const snap={setup_id:r.symbol+'-'+EX.timeframe+'-'+EX.symbol, setup_version:1, symbol:r.symbol,
    side:(e.direction||(r.aligned_up?'LONG':'SHORT')), score:null,
    signal:(r.momentum||'')+' / '+(r.trend||''), entry:e.trigger||r.price,
    invalidation:e.invalidation, target:e.target, risk_reward:e.reward_risk, factors:{},
    source:r.bar_source, quote_source:r.price_source, timeframe:EX.timeframe,
    rule_version:r.rule_version, sector_parent:EX.symbol, sector_universe:EX.universe,
    publication_state:'RESEARCH_ONLY', executable:false, captured_at:new Date().toISOString()};
  try{localStorage.setItem('qx.selectedSetup',JSON.stringify(snap))}catch(err){}
  location.href='/trade';
}
$('#extf').addEventListener('change',function(){ if(EX) exploreSector(EX.symbol); });
$('#exuniverse').addEventListener('change',function(){ if(EX) exploreSector(EX.symbol); });
"""
