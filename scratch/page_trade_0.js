
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
