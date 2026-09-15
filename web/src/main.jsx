import React, {useState, useEffect, useRef, lazy, Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import {RefreshCw} from 'lucide-react';
import './style.css';
import './dashboard.css';
import Holdings from './Holdings';
import ReferenceRanking from './ReferenceRanking';
import useAnalytics from './useAnalytics';
import LiveRefresh from './LiveRefresh';
import MoversWorkspace from './MoversWorkspace';
import AIReview from './AIReview';
import {workspaceContext,workspaceHref,updateWorkspaceContext} from './workspace-context';
import WorkspaceNavigation from './WorkspaceNavigation';
import {resolveWorkspaceRoute} from './workspace-routes';
import QXTradingSuite from './QXTradingSuite';
import QXDayTraderTerminal from './QXDayTraderTerminal';
import SPXFuturesWorkspace from './SPXFuturesWorkspace';
import QXDailyNewsPrompt from './QXDailyNewsPrompt';
import QXInstitutionalScanner from './QXInstitutionalScanner';
import QXOptionsScanner from './QXOptionsScanner';
import QXOptionsIdeas from './QXOptionsIdeas';
import QXPositionAdvisor from './QXPositionAdvisor';
import QXResearchStudio from './QXResearchStudio';
import QXStrategyWorkspaces from './QXStrategyWorkspaces';
import QXSystemControl from './QXSystemControl';
import QXBentoDashboardLayout from './QXBentoDashboardLayout';
import { ErrorBoundary } from './ErrorBoundary';



const RSLine = lazy(()=>import('./RSLine'));
const percent = n => Number.isFinite(n) ? `${n >= 0 ? '+' : ''}${(n*100).toFixed(2)}%` : '—';

function App() {
 const [search,setSearch]=useState(()=>location.search);
 useEffect(()=>{
  const restore=()=>setSearch(location.search);
  window.addEventListener('popstate',restore);
  window.addEventListener('workspacecontextchange',restore);
  return()=>{window.removeEventListener('popstate',restore);window.removeEventListener('workspacecontextchange',restore);};
 },[]);
 const query=new URLSearchParams(search);
 const context=workspaceContext(search);
 const route=resolveWorkspaceRoute(query.get('page')||'relative_strength');

 useEffect(()=>{
  if(!context.etf||!context.symbol){
   updateWorkspaceContext({etf:context.etf||'XLK',symbol:context.symbol||context.etf||'XLK'},{replace:true});
  }
 },[context.etf,context.symbol]);

 if(!route) return (
  <QXBentoDashboardLayout route={{workspace:'Markets',title:'Relative Strength',page:'relative_strength'}} context={context}>
   <p role="alert">Workspace page unavailable. <a href={workspaceHref('relative_strength',context)}>Return to Markets</a></p>
  </QXBentoDashboardLayout>
 );

 const pageKey = route.page;

 if (pageKey === 'spx_nq_futures') {
  return (
   <QXBentoDashboardLayout route={route} context={context}>
    <div style={{ width: '100%', gridColumn: 'span 12' }}>
     <ErrorBoundary title="SPX & Futures Command Dashboard">
       <SPXFuturesWorkspace />
     </ErrorBoundary>
    </div>
   </QXBentoDashboardLayout>
  );
 }


 if (pageKey === 'scan' || pageKey === 'broad_watchlist' || pageKey === 'heatmap') {
  return (
   <QXBentoDashboardLayout route={route} context={context}>
    <div style={{ width: '100%', gridColumn: 'span 12' }}>
     <ErrorBoundary title="QX Institutional Scanner">
       <QXInstitutionalScanner onSelectSymbol={val => updateWorkspaceContext({symbol: val, etf: val})} />
     </ErrorBoundary>
     <div style={{ marginTop: '32px' }}>
       <ErrorBoundary title="QX Options Scanner">
         <QXOptionsScanner defaultSymbol={context.symbol || 'NVDA'} onSelectSymbol={val => updateWorkspaceContext({symbol: val})} />
       </ErrorBoundary>
     </div>
     <div style={{ marginTop: '32px' }}>
       <ErrorBoundary title="QX Options Ideas Hub">
         <QXOptionsIdeas />
       </ErrorBoundary>
     </div>
    </div>
   </QXBentoDashboardLayout>
  );
 }

 if (pageKey === 'command_center' || pageKey === 'morning_report' || pageKey === 'daily_workflow') {
  return (
   <QXBentoDashboardLayout route={route} context={context}>
    <div style={{ width: '100%', gridColumn: 'span 12' }}>
     <ErrorBoundary title="QX Day Trader Terminal">
       <QXDayTraderTerminal activeSymbol={context.symbol||'XLK'} onSelectSymbol={val => updateWorkspaceContext({symbol: val})} />
     </ErrorBoundary>
     <ErrorBoundary title="QX Daily News & Prompt Deck">
       <QXDailyNewsPrompt />
     </ErrorBoundary>
    </div>
   </QXBentoDashboardLayout>
  );
 }

 if (pageKey === 'ticker_history' || pageKey === 'options_ideas' || pageKey === 'options_flow' || pageKey === 'liquidity_map' || pageKey === 'backtest' || pageKey === 'strategy_lab') {
  return (
   <QXBentoDashboardLayout route={route} context={context}>
    <div style={{ width: '100%', gridColumn: 'span 12' }}>
     <ErrorBoundary title="QX Research Studio">
       <QXResearchStudio defaultSymbol={context.symbol||'XLK'} />
     </ErrorBoundary>
     <ErrorBoundary title="QX Options Ideas">
       <QXOptionsIdeas />
     </ErrorBoundary>
     <ErrorBoundary title="QX Strategy Workspaces">
       <QXStrategyWorkspaces />
     </ErrorBoundary>
    </div>
   </QXBentoDashboardLayout>
  );
 }

 if (pageKey === 'idea_tracking' || pageKey === 'journal') {
  return (
   <QXBentoDashboardLayout route={route} context={context}>
    <div style={{ width: '100%', gridColumn: 'span 12' }}>
     <ErrorBoundary title="QX Position Research & Action Advisor">
       <QXPositionAdvisor defaultSymbol={context.symbol||'XLK'} />
     </ErrorBoundary>
    </div>
   </QXBentoDashboardLayout>
  );
 }

 if (route?.workspace === 'System' || pageKey === 'schwab' || pageKey === 'data_cache' || pageKey === 'jobs' || pageKey === 'run_history' || pageKey === 'strategy_rules') {
  return (
   <QXBentoDashboardLayout route={route} context={context}>
    <div style={{ width: '100%', gridColumn: 'span 12' }}>
     <ErrorBoundary title="QX System Operations Control">
       <QXSystemControl currentSubRoute={pageKey} />
     </ErrorBoundary>
    </div>
   </QXBentoDashboardLayout>
  );
 }


 return <MarketsDashboard context={context} route={route}/>;
}

function MarketsDashboard({context}) {
 const symbol=context.etf||'XLK';
 const [revision,setRevision]=useState(0);
 const [hydrated, setHydrated] = useState(false);
 const [progress, setProgress] = useState(25);
 const [step, setStep] = useState(1);
 const pendingAnchor=useRef(Boolean(location.hash));
 const {data,error,busy}=useAnalytics(revision);

 function chooseSymbol(value, jump=false){
   updateWorkspaceContext({etf:value,...(jump||!context.symbol?{symbol:value}:{})});
   if(jump)document.getElementById('etf-detail')?.scrollIntoView({block:'start'});
 }

 useEffect(() => {
   let isMounted = true;
   const p1 = fetch('/api/terminal/watchlist').catch(() => {});
   const p2 = fetch('/api/spx-dashboard').catch(() => {});
   const p3 = fetch('/api/spx-calendars').catch(() => {});

   const timer1 = setTimeout(() => { if (isMounted) { setProgress(65); setStep(2); } }, 200);
   const timer2 = setTimeout(() => { if (isMounted) { setProgress(90); setStep(3); } }, 400);

   Promise.allSettled([p1, p2, p3]).finally(() => {
     if (isMounted) {
       setProgress(100);
       setTimeout(() => {
         if (isMounted) setHydrated(true);
       }, 250);
     }
   });

   return () => { isMounted = false; clearTimeout(timer1); clearTimeout(timer2); };
 }, []);

 const requestedDateMismatch=Boolean(context.as_of&&data?.benchmark_metrics?.as_of?.slice(0,10)!==context.as_of);
 const visibleData=requestedDateMismatch?null:data;
 const selected=visibleData?.rows.find(row=>row.etf===symbol);

 useEffect(()=>{
  if(!pendingAnchor.current||busy)return;
  const target=document.getElementById(location.hash.slice(1));
  const container=target?.closest('main');
  if(!container)return;
  pendingAnchor.current=false;
  let frame;
  const align=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));};
  const observer=new ResizeObserver(align);
  observer.observe(container);
  const events=['wheel','touchstart','pointerdown','keydown','hashchange','popstate'];
  const release=()=>{observer.disconnect();cancelAnimationFrame(frame);events.forEach(event=>window.removeEventListener(event,release));};
  events.forEach(event=>window.addEventListener(event,release,{passive:true}));
  align();
  return release;
 },[data,busy,selected]);

 const benchmark=visibleData?.benchmark_metrics;

 if (!hydrated) {
   return (
     <div className="qx-preloader-overlay">
       <div className="qx-preloader-card">
         <div className="qx-preloader-badge">QX OS ARCHITECTURE</div>
         <h2 className="qx-preloader-title">Hydrating Quantitative Engine</h2>
         <p className="qx-preloader-sub">
           Pre-loading live Schwab market streams, 0DTE dealer GEX matrices & SPX calendar structures...
         </p>
         <div className="qx-preloader-bar-bg">
           <div className="qx-preloader-bar-fill" style={{ width: `${progress}%` }}></div>
         </div>
         <div className="qx-preloader-steps">
           <div className={`qx-preloader-step ${step >= 1 ? 'active' : ''}`}>
             <span>{step >= 1 ? '✓' : '○'}</span> 1. Realtime Stock & Index Baselines
           </div>
           <div className={`qx-preloader-step ${step >= 2 ? 'active' : ''}`}>
             <span>{step >= 2 ? '✓' : '○'}</span> 2. SPX Option Calendars & GEX Pinning
           </div>
           <div className={`qx-preloader-step ${step >= 3 ? 'active' : ''}`}>
             <span>{step >= 3 ? '✓' : '○'}</span> 3. Sector Relative Strength & AI Contracts
           </div>
         </div>
       </div>
     </div>
   );
 }

 return (
  <QXBentoDashboardLayout route={route} context={context}>
   <div style={{ width: '100%', gridColumn: 'span 12' }}>
    <header className="reference-header"><div><div className="title-line"><h1>QX Quantitative Trading Workspace</h1><span className="badge" style={{background:'#3b82f6',color:'#fff'}}>QX OS</span></div><p>Verified Relative Strength, Market Movers & Evidence-Backed Intraday Intelligence{benchmark?` · available through ${benchmark.as_of.slice(0,10)}`:''}</p></div>
     <div className="head-actions">{[['SPY MTD',percent(benchmark?.mtd)],['SPY 21D',percent(benchmark?.return_21d)],['COVERAGE',data?`${data.coverage}/${data.universe}`:'—'],['SESSIONS',benchmark?.sessions??'—']].map(([label,value],i)=><div className="header-stat" key={label}><small>{label}</small><strong className={i<2&&value!=='—'?(String(value).startsWith('-')?'negative':'positive'):''}>{value}</strong></div>)}<button disabled={busy} onClick={()=>setRevision(r=>r+1)} title="Reload cached analytics" aria-label="Reload cached analytics"><RefreshCw size={15} className={busy?'spin':''}/></button></div>
    </header>
    {!context.as_of&&<LiveRefresh onComplete={()=>setRevision(r=>r+1)}/>}
    {visibleData?.rows.length>0&&!selected&&<div role="status" className="coverage-note">No ETF detail is available for {symbol} in this dataset. <button onClick={()=>chooseSymbol('XLK')}>Select XLK</button></div>}

    <nav className="section-nav" aria-label="Dashboard sections"><a href="#ranking">Sector ranking</a><a href="#movers">Market movers</a><a href="#position-advisor">Position Advisor</a><a href="#research-studio">Research Studio</a><a href="#strategy-workspaces">Strategy Workspaces</a>{selected&&<><a href="#etf-detail">RS chart</a><a href="#ai-review">AI review</a><a href="#holdings">Holdings</a></>}<a href="#options-ideas-hub">Options Ideas Hub</a><a href="#options-scanner-v1">Options Scanner V1</a><a href="#qx-terminal">Day Trader Terminal</a><a href="#daily-prompt">Master Prompt</a><a href="#scanner-studio">AI Scanner Studio</a></nav>

    {/* PRIMARY VERIFIED RELATIVE STRENGTH & MARKET MOVERS DASHBOARD */}
    {requestedDateMismatch?<div role="alert" className="coverage-note">No matching relative-strength snapshot for {context.as_of}. Current data has not been substituted. <button onClick={()=>updateWorkspaceContext({as_of:'',snapshot:''})}>Use latest session</button></div>:<>
    <ErrorBoundary title="Sector Relative Strength Ranking">
      <ReferenceRanking onSelect={value=>chooseSymbol(value,true)} data={visibleData} error={error} busy={busy} onRetry={()=>setRevision(r=>r+1)} symbol={symbol}/>
    </ErrorBoundary>
    <ErrorBoundary title="Market Movers Workspace">
      <MoversWorkspace data={visibleData} revision={revision} onSelect={value=>chooseSymbol(value,true)}/>
    </ErrorBoundary>
    </>}

    {/* AUTOMATED POSITION RESEARCH & ACTION ADVISOR */}
    <ErrorBoundary title="Position Research & Action Advisor">
      <QXPositionAdvisor defaultSymbol={context.symbol||symbol} />
    </ErrorBoundary>
    <ErrorBoundary title="Underlying Setup & Structure Research Studio">
      <QXResearchStudio defaultSymbol={context.symbol||symbol} />
    </ErrorBoundary>
    <ErrorBoundary title="Modular Strategy Workspaces & Leg Payoff Engine">
      <QXStrategyWorkspaces />
    </ErrorBoundary>

    {selected&&<><section className="detail chart-detail" id="etf-detail"><div className="section-head"><h2>{symbol} · {selected.sector} — RS Line vs SPY</h2><div className="etf-tabs" role="group" aria-label="Chart ETF">{data.rows.map(row=><button key={row.etf} aria-pressed={symbol===row.etf} title={row.sector} onClick={()=>chooseSymbol(row.etf)}>{row.etf}</button>)}</div><select className="mobile-etf-select" aria-label="Chart ETF selection" value={symbol} onChange={event=>chooseSymbol(event.target.value)}>{data.rows.map(row=><option key={row.etf} value={row.etf}>{row.etf} · {row.sector}</option>)}</select></div>
      <Suspense fallback={<div className="chart-placeholder"><p role="status">Loading chart…</p></div>}>
        <ErrorBoundary title="Relative Strength Chart">
          <RSLine key={`${symbol}-${revision}`} symbol={symbol}/>
        </ErrorBoundary>
      </Suspense>
     </section>
     <ErrorBoundary title="AI Evidence Review">
       <AIReview key={`ai-${symbol}-${revision}`} symbol={symbol} revision={revision}/>
     </ErrorBoundary>
     <ErrorBoundary title="Fund Holdings Analysis">
       <Holdings key={`holdings-${symbol}-${revision}`} symbol={symbol}/>
     </ErrorBoundary>
     </>}

    {/* SECONDARY INTRADAY WORKSPACES & COMMAND TERMINALS */}
    <div style={{ marginTop: '32px', paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
      <h2 style={{ fontSize: '18px', color: '#38bdf8', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        ⚡ QX Execution Terminals & Intraday Workspaces
      </h2>
      <ErrorBoundary title="QX Day Trader Terminal">
        <QXDayTraderTerminal activeSymbol={context.symbol||symbol} onSelectSymbol={val => chooseSymbol(val, true)} />
      </ErrorBoundary>
      <ErrorBoundary title="SPX & Futures Command Dashboard">
        <SPXFuturesWorkspace />
      </ErrorBoundary>
      <ErrorBoundary title="QX Daily Market News & Prompt Studio">
        <QXDailyNewsPrompt symbol={context.symbol||symbol} />
      </ErrorBoundary>
      <ErrorBoundary title="QX Options Value & LEAPS Workbench">
        <QXOptionsIdeas onSelectSymbol={val => chooseSymbol(val, true)} />
      </ErrorBoundary>
      <ErrorBoundary title="QX Process-Driven Options Scanner V1">
        <QXOptionsScanner defaultSymbol={context.symbol||symbol} onSelectSymbol={val => chooseSymbol(val, true)} />
      </ErrorBoundary>
      <ErrorBoundary title="QX Institutional AI Scanner Studio">
        <QXInstitutionalScanner onSelectSymbol={val => chooseSymbol(val, true)} />
      </ErrorBoundary>
      <ErrorBoundary title="QX Intelligence Suite">
        <QXTradingSuite symbol={context.symbol||symbol}/>
      </ErrorBoundary>
    </div>

    <footer>QX OS · Quantitative Breakout & Options Intelligence · No financial advice.</footer>
   </div>
  </QXBentoDashboardLayout>
 );
}
createRoot(document.getElementById('root')).render(<App/>);
