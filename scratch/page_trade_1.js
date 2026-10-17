

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
