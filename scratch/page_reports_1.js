
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const money=v=>v==null?'—':(v<0?'-$':'$')+Math.abs(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const cls=v=>v==null?'':(v>0?'up':v<0?'dn':'');
const pct=v=>v==null?'—':(v*100).toFixed(1)+'%';
const num=(v,d=2)=>v==null?'—':Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
// Times are shown in EXCHANGE time (US/Eastern), never UTC — consistent with every
// other page. A trader reads market time, not the host's zone or raw UTC.
const EXCHANGE_TZ='America/New_York';
function exStamp(v){
  if(v==null||v==='')return 'time unavailable';
  const d=new Date(v); if(isNaN(d.getTime()))return 'time unavailable';
  return d.toLocaleTimeString('en-US',{timeZone:EXCHANGE_TZ,hour12:false,hour:'2-digit',
    minute:'2-digit',second:'2-digit'})+' ET';
}
async function j(u){const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status+' '+(await r.text()).slice(0,200));return r.json()}
function table(cols,rows,empty){
  if(!rows||!rows.length)return '<span class="mut">'+esc(empty||'No data in this window.')+'</span>';
  return '<table><thead><tr>'+cols.map(c=>'<th'+(c.num?' class="num"':'')+'>'+esc(c.h)+'</th>').join('')+
    '</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>'<td'+(c.num?' class="num"':'')+'>'+c.f(r)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
}
function kpi(label,value,sub,klass){return '<div class="kpi"><span>'+esc(label)+'</span><b class="'+klass+'">'+value+'</b><em>'+esc(sub||'')+'</em></div>'}
function splitHtml(d){
  const s=d.trade_split||{}, rows=s.rows||[];
  if(!rows.length)return '<span class="mut">No closed trades to split.</span>';
  const o=s.options||{},k=s.stocks||{},f=s.futures||{},fu=s.funds||{};
  const total=s.total_realized||0;
  let h='<div class="kpis">'
   +kpi('Options',money(o.realized),(o.trades||0)+' trades · '+pct(o.win_rate)+' win',cls(o.realized))
   +kpi('Stocks',money(k.realized),(k.trades||0)+' trades · '+pct(k.win_rate)+' win',cls(k.realized))
   +kpi('Futures',money(f.realized),(f.trades||0)+' trades',cls(f.realized))
   +kpi('Funds',money(fu.realized),(fu.trades||0)+' trades',cls(fu.realized))
   +kpi('Total realized',money(total),'gross, before fees',cls(total))+'</div>';
  h+='<div style="margin-top:10px">'+table(
    [{h:'Type',f:r=>'<b>'+esc(r.name)+'</b>'},
     {h:'Realized',num:1,f:r=>'<span class="'+cls(r.realized)+'">'+money(r.realized)+'</span>'},
     {h:'Share',num:1,f:r=>r.share_of_realized==null?'—':pct(r.share_of_realized)},
     {h:'Trades',num:1,f:r=>num(r.trades,0)},
     {h:'Win rate',num:1,f:r=>pct(r.win_rate)},
     {h:'Avg / trade',num:1,f:r=>'<span class="'+cls(r.avg_per_trade)+'">'+money(r.avg_per_trade)+'</span>'},
     {h:'Profit factor',num:1,f:r=>r.profit_factor==null?'—':num(r.profit_factor)},
     {h:'Symbols',num:1,f:r=>num(r.symbols,0)}],rows)+'</div>';
  return h;
}
function dayTable(days){
  return table(
    [{h:'Day',f:r=>'<b>'+esc(r.key)+'</b>'},
     {h:'Realized',num:1,f:r=>'<span class="'+cls(r.realized)+'">'+money(r.realized)+'</span>'},
     {h:'Trades',num:1,f:r=>num(r.trades,0)},
     {h:'W/L',num:1,f:r=>(r.wins||0)+'/'+(r.losses||0)},
     {h:'Options',num:1,f:r=>r.options?'<span class="'+cls(r.options)+'">'+money(r.options)+'</span>':'—'},
     {h:'Stocks',num:1,f:r=>r.equity?'<span class="'+cls(r.equity)+'">'+money(r.equity)+'</span>':'—'},
     {h:'Futures',num:1,f:r=>r.futures?'<span class="'+cls(r.futures)+'">'+money(r.futures)+'</span>':'—'},
     {h:'Best',f:r=>r.best?esc(r.best.symbol)+' '+money(r.best.realized):'—'},
     {h:'Worst',f:r=>r.worst?esc(r.worst.symbol)+' '+money(r.worst.realized):'—'}],
    days,'No realized trades in this window.');
}
function monthlyTable(d,uid){
  const months=d.by_month||[], days=d.month_days||{};
  const ns=uid?uid+'-':'';
  if(!months.length)return '<span class="mut">No monthly data.</span>';
  let h='<div class="tablewrap"><table><thead><tr><th></th><th>Month</th><th class="num">Realized</th>'
   +'<th class="num">Trades</th><th class="num">W/L</th><th class="num">Options</th><th class="num">Stocks</th>'
   +'<th class="num">Futures</th><th>Best</th><th>Worst</th></tr></thead><tbody>';
  months.forEach(function(m,i){
    const kid=ns+'md-'+i;
    h+='<tr style="cursor:pointer" onclick="toggleMonth(&quot;'+kid+'&quot;)">'
     +'<td id="'+kid+'-c">&#9656;</td><td><b>'+esc(m.key)+'</b></td>'
     +'<td class="num"><span class="'+cls(m.realized)+'">'+money(m.realized)+'</span></td>'
     +'<td class="num">'+num(m.trades,0)+'</td><td class="num">'+(m.wins||0)+'/'+(m.losses||0)+'</td>'
     +'<td class="num">'+(m.options?'<span class="'+cls(m.options)+'">'+money(m.options)+'</span>':'—')+'</td>'
     +'<td class="num">'+(m.equity?'<span class="'+cls(m.equity)+'">'+money(m.equity)+'</span>':'—')+'</td>'
     +'<td class="num">'+(m.futures?'<span class="'+cls(m.futures)+'">'+money(m.futures)+'</span>':'—')+'</td>'
     +'<td>'+(m.best?esc(m.best.symbol):'—')+'</td><td>'+(m.worst?esc(m.worst.symbol):'—')+'</td></tr>';
    h+='<tr id="'+kid+'" style="display:none"><td></td><td colspan="9">'
     +'<div class="mut" style="margin-bottom:6px">Days in '+esc(m.key)+'</div>'
     +'<div class="scroll" style="max-height:260px">'+dayTable(days[m.key]||[])+'</div>'
     +'<div class="mut" style="margin-top:8px">Symbols traded in '+esc(m.key)+'</div>'
     +'<div style="margin-top:4px">'+table([{h:'Symbol',f:r=>'<b>'+esc(r.symbol)+'</b>'},
        {h:'Realized',num:1,f:r=>'<span class="'+cls(r.realized)+'">'+money(r.realized)+'</span>'},
        {h:'Trades',num:1,f:r=>num(r.trades,0)}],m.symbols||[],'—')+'</div>'
     +'</td></tr>';
  });
  return h+'</tbody></table></div>';
}
function toggleMonth(id){
  const row=document.getElementById(id); if(!row)return;
  const open=row.style.display!=='none';
  row.style.display=open?'none':'table-row';
  const caret=document.getElementById(id+'-c');
  if(caret)caret.innerHTML=open?'&#9656;':'&#9662;';
}
function reportHtml(d,uid){
  const ns=uid?uid+'-':'';
  const t=d.totals||{},p=d.performance||{},b=d.balances||{},a=d.account||{},q=d.quality||{};
  let h='';
  if(q.truncated)h+='<div class="banner" style="margin-bottom:10px">Transaction window truncated in: '+esc(q.truncated_windows.join(', '))+' — increase the window granularity for full history.</div>';
  if(q.errors&&q.errors.length)h+='<div class="banner err" style="margin-bottom:10px">'+q.errors.length+' window error(s): '+esc(q.errors.slice(0,3).join(' · '))+'</div>';
  h+='<div class="card"><h2>Account '+esc(a.label||a.type||'')+' '+esc(a.masked||'')+' · equity as of '+esc(exStamp(d.generated_at))+'</h2><div class="kpis">'
   +kpi('Equity',money(b.equity),'liquidation value')
   +kpi('Cash',money(b.cash),'buying power '+money(b.buying_power))
   +kpi('Realized (net)',money(t.realized_net),'gross '+money(t.realized_gross),cls(t.realized_net))
   +kpi('Unrealized',money(t.unrealized),'open positions',cls(t.unrealized))
   +kpi('Day P&L',money(t.day_pnl),'current session',cls(t.day_pnl))
   +kpi('Total P&L',money(t.total_pnl),'realized net + unrealized',cls(t.total_pnl))
   +kpi('Income',money(t.income),'dividends / interest')
   +kpi('Fees',money(t.fees),'commissions & regulatory')
   +'</div></div>';
  h+='<div class="card"><h2>Performance · '+esc(String(p.closed_trades||0))+' closed trades</h2><div class="kpis">'
   +kpi('Win rate',pct(p.win_rate),(p.wins||0)+'W / '+(p.losses||0)+'L')
   +kpi('Avg win',money(p.avg_win),'per winning trade',cls(1))
   +kpi('Avg loss',money(p.avg_loss),'per losing trade','dn')
   +kpi('Profit factor',p.profit_factor==null?'—':num(p.profit_factor),'gross win / gross loss')
   +'</div></div>';
  h+='<div class="card"><h2>Options vs Stocks &mdash; realized by trade type</h2><div id="'+ns+'split">'+splitHtml(d)+'</div></div>';
  h+='<div class="grid2">';
  const maxAbs=Math.max(1,...(d.by_asset_type||[]).map(r=>Math.abs(r.realized)));
  h+='<div class="card"><h2>P&amp;L by trade type</h2>'+table(
    [{h:'Type',f:r=>esc(r.label)},{h:'Realized',num:1,f:r=>'<span class="'+cls(r.realized)+'">'+money(r.realized)+'</span>'},
     {h:'Trades',num:1,f:r=>num(r.trades,0)},{h:'W/L',num:1,f:r=>(r.wins||0)+'/'+(r.losses||0)},
     {h:'Weight',f:r=>'<div class="bar"><i style="width:'+(Math.abs(r.realized)/maxAbs*100).toFixed(1)+'%;background:'+(r.realized<0?'var(--dn)':'var(--up)')+'"></i></div>'}],
    d.by_asset_type,'No closed trades by type.')+'</div>';
  const sym=(d.by_symbol||[]).slice(0,12);
  h+='<div class="card"><h2>P&amp;L by symbol (top 12)</h2>'+table(
    [{h:'Symbol',f:r=>'<b>'+esc(r.name)+'</b>'},{h:'Realized',num:1,f:r=>'<span class="'+cls(r.realized)+'">'+money(r.realized)+'</span>'},
     {h:'Trades',num:1,f:r=>num(r.trades,0)},{h:'Win rate',num:1,f:r=>pct(r.win_rate)}],
    sym,'No realized trades.')+'</div>';
  h+='</div>';
  h+='<div class="card"><h2>Monthly realized P&amp;L &mdash; click a month to drill into days</h2>'
   +'<div class="mut" style="font-size:12px;margin-bottom:8px">Totals are per account; nothing is combined across accounts.</div>'
   +monthlyTable(d,uid)+'</div>';
  h+='<div class="card"><h2>Daily realized P&amp;L &mdash; all days in window</h2>'
   +'<div class="scroll">'+dayTable(d.by_day||[])+'</div></div>';
  h+='<div class="card"><h2>Open positions · unrealized</h2>'+table(
    [{h:'Symbol',f:r=>'<b>'+esc(r.symbol)+'</b>'},{h:'Type',f:r=>'<span class="chip">'+esc(r.asset_label)+'</span>'},
     {h:'Qty',num:1,f:r=>num(r.quantity,4)},{h:'Avg',num:1,f:r=>money(r.average_price)},
     {h:'Mkt value',num:1,f:r=>money(r.market_value)},{h:'Cost basis',num:1,f:r=>money(r.cost_basis)},
     {h:'Unrealized',num:1,f:r=>'<span class="'+cls(r.unrealized)+'">'+money(r.unrealized)+'</span>'},
     {h:'%',num:1,f:r=>r.unrealized_pct==null?'—':num(r.unrealized_pct)+'%'},
     {h:'Day',num:1,f:r=>'<span class="'+cls(r.day_pnl)+'">'+money(r.day_pnl)+'</span>'}],
    d.positions,'No open positions.')+'</div>';
  if((d.open_lots||[]).length){
    h+='<div class="card"><h2>Open lots carried from trades (FIFO)</h2>'+table(
      [{h:'Symbol',f:r=>'<b>'+esc(r.symbol)+'</b>'},{h:'Type',f:r=>'<span class="chip">'+esc(r.asset_type)+'</span>'},
       {h:'Qty',num:1,f:r=>num(r.qty,4)},{h:'Cost / unit (cash)',num:1,f:r=>money(r.cost_per_unit)}],
      d.open_lots)+'</div>';
  }
  h+='<div class="card"><h2>Transactions · '+esc(String(d.transaction_count||0))+' in window (showing '+(d.transactions||[]).length+')</h2><div class="scroll">'
   +table([{h:'Time',f:r=>esc((r.time||'').slice(0,19).replace('T',' '))},
     {h:'Type',f:r=>'<span class="chip">'+esc(r.type)+'</span>'},
     {h:'Symbol',f:r=>esc(r.symbol||'—')},
     {h:'Desc',f:r=>'<span class="mut">'+esc((r.description||'').slice(0,42))+'</span>'},
     {h:'Effect',f:r=>r.position_effect?'<span class="chip '+esc(r.position_effect)+'">'+esc(r.position_effect)+'</span>':'—'},
     {h:'Qty',num:1,f:r=>r.quantity==null?'—':num(r.quantity,4)},
     {h:'Price',num:1,f:r=>r.price==null?'—':money(r.price)},
     {h:'Cost',num:1,f:r=>r.cost==null?'—':money(r.cost)},
     {h:'Fees',num:1,f:r=>r.fees?money(r.fees):'—'},
     {h:'Net cash',num:1,f:r=>'<span class="'+cls(r.net_amount)+'">'+money(r.net_amount)+'</span>'}],
    d.transactions,'No transactions in this window.')+'</div></div>';
  h+='<div class="card"><h2>Data quality</h2><div class="mut" style="font-size:12px">'
   +'Cost method: '+esc(q.cost_method||'')+' · windows fetched: '+esc(String(q.windows||0))
   +' · request window: '+esc(String(d.window_days))+' days'
   +((d.unmatched_closes||[]).length?' · <span class="warn">'+d.unmatched_closes.length+' closing leg(s) without a matched opening lot (partial history)</span>':'')
   +'</div></div>';
  return h;
}
async function load(noCache){
  $('#status').textContent='loading…';$('#alerts').innerHTML='';
  const days=$('#days').value, acct=$('#acct').value, q=noCache?'&nocache=1':'';
  try{
    if(acct==='__ALL__'){
      const a=await j('/api/accounts');
      const list=a.accounts||[];
      const reps=await Promise.all(list.map(x=>j('/api/report?account='+encodeURIComponent(x.account_number)+'&days='+days+q)));
      $('#body').innerHTML='<div class="banner" style="border-color:var(--acc);background:rgba(76,141,255,.07);color:var(--fg)">'
        +'Accounts are reported independently and are never combined or netted. Each block below is a complete per-account report.</div>'
        +reps.map(function(d,i){var acc=list[i]||{};
          if(d&&d.error){return '<div class="acctblock"><div class="accthead"><b>'+esc(acc.label||acc.type||'Account')+' '+esc(acc.masked||'')+'</b></div><div class="banner err">'+esc(d.error)+'</div></div>';}
          return '<div class="acctblock"><div class="accthead"><b>'+esc(acc.label||acc.type||'Account')+' '+esc(acc.masked||'')+'</b>'
            +'<span class="chip">kept separate</span></div>'+reportHtml(d,'acct'+i)+'</div>';}).join('');
      $('#stamp').textContent='read-only · '+reps.length+' accounts · generated '+exStamp((reps[0]||{}).generated_at);
    } else {
      const d=await j('/api/report?account='+encodeURIComponent(acct)+'&days='+days+q);
      if(d&&d.error){
        $('#body').innerHTML='<div class="banner err">Broker read failed: '+esc(d.error)
          +'<div class="mut" style="margin-top:6px">This is an upstream Schwab error (for example a transient 503), not a report failure. Retry shortly.</div></div>';
        $('#status').textContent='error';return;
      }
      $('#body').innerHTML=reportHtml(d,'one');
      $('#stamp').textContent='read-only · generated '+exStamp(d.generated_at);
    }
    $('#status').textContent='ok';
  }catch(e){$('#status').textContent='error';$('#alerts').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
async function boot(){
  try{
    const a=await j('/api/accounts');
    $('#acct').innerHTML='<option value="__ALL__">All accounts — kept separate</option>'+(a.accounts||[]).map(x=>'<option value="'+esc(x.account_number)+'">'+esc(x.label||x.type||'Account')+' '+esc(x.masked)+'</option>').join('');
    if(!(a.accounts||[]).length){$('#body').innerHTML='<div class="banner err">No accounts returned by the token.</div>';return}
    if(a.warnings&&a.warnings.length)$('#alerts').innerHTML=a.warnings.map(w=>'<div class="banner">'+esc(w)+'</div>').join('');
    load();
  }catch(e){$('#body').innerHTML='<div class="banner err">'+esc(e.message)+'</div>'}
}
$('#days').addEventListener('change',load);
boot();
