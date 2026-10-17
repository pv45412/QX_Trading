import React, {useEffect, useMemo, useState} from 'react';
import {Activity, BookOpenCheck, CalendarClock, Database, KeyRound, RefreshCw, Server, ShieldCheck} from 'lucide-react';
import {workspaceHref} from './workspace-context';
import {isQxSystemFixtureEnabled} from './qx-v2-feature';
import {buildSystemJobStatus, buildSystemOverview, systemTabForRoute} from './qx-system-model';
import {fetchSystemJobStatus, fetchSystemOverview} from './qx-system-client';
import QXDataEvidence, {evidenceAttributes} from './QXDataEvidence';
import {
  clearSchwabCredentials,
  completeSchwabAuthentication,
  getSchwabCredentialStatus,
  getSchwabOAuthUrl,
  saveSchwabCredentials,
  testSchwabConnection,
} from './schwab-credentials-client';

const EMPTY_SCHWAB_STATUS = {configured: false, client_id_last4: null, redirect_uri: 'https://127.0.0.1',
  oauth_status: 'UNAUTHENTICATED', refresh_token_status: 'UNAVAILABLE', provider_health: 'UNAVAILABLE', last_verified_at: null};
const tabDefinitions = [
  ['overview', 'Overview', Server, 'system'],
  ['providers', 'Providers', KeyRound, 'schwab'],
  ['data', 'Data', Database, 'data_cache'],
  ['jobs', 'Jobs', CalendarClock, 'jobs'],
  ['runs', 'Runs', Activity, 'run_history'],
  ['rules', 'Rules', BookOpenCheck, 'strategy_rules'],
];

export default function QXSystemControl({currentSubRoute='system_overview', context={}}) {
  const [activeTab, setActiveTab] = useState(() => systemTabForRoute(currentSubRoute));
  const [overviewState, setOverviewState] = useState({data: null, loading: true, error: ''});
  const [jobState, setJobState] = useState({data: null, loading: false, error: ''});
  const query = new URLSearchParams(location.search);
  const fixture = isQxSystemFixtureEnabled() && query.get('system_fixture') === '1';

  useEffect(() => setActiveTab(systemTabForRoute(currentSubRoute)), [currentSubRoute]);
  useEffect(() => { loadOverview(); }, []);
  useEffect(() => { if (activeTab === 'jobs' && !jobState.data && !jobState.loading) loadJobs(); }, [activeTab]);

  const loadOverview = async () => {
    const controller = new AbortController();
    setOverviewState(previous => ({...previous, loading: true, error: ''}));
    try { setOverviewState({data: buildSystemOverview(await fetchSystemOverview({signal: controller.signal})), loading: false, error: ''}); }
    catch (error) { setOverviewState(previous => ({...previous, loading: false, error: error.message})); }
  };
  const loadJobs = async () => {
    const controller = new AbortController();
    setJobState(previous => ({...previous, loading: true, error: ''}));
    try { setJobState({data: buildSystemJobStatus(await fetchSystemJobStatus({signal: controller.signal})), loading: false, error: ''}); }
    catch (error) { setJobState(previous => ({...previous, loading: false, error: error.message})); }
  };
  const navigate = (tab, route) => {
    setActiveTab(tab);
    const url = new URL(workspaceHref(route, context), location.origin);
    history.pushState(history.state, '', `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new Event('workspacecontextchange'));
  };

  const overview = overviewState.data || buildSystemOverview(null);
  return <article className="qx-system-workspace" aria-label="System workspace"
    {...evidenceAttributes({source: 'QX system status APIs', dataAsOf: overview.generatedAt, freshness: 'CURRENT_REQUEST'})}>
    <header className="qx-system-header">
      <div><span className="eyebrow">SYSTEM / READ-ONLY OPERATIONS</span><h1><Server size={22}/> System</h1>
        <p>Provider readiness, local data inventory, scheduler state, persisted runs, and configuration metadata.</p></div>
      <div className="qx-system-header-badges">
        <StatusBadge value={overview.status}/>
        {fixture && <strong className="qx-preview-badge">TEST / PREVIEW DATA - NOT LIVE</strong>}
      </div>
    </header>

    <nav className="qx-system-tabs" aria-label="System views">
      {tabDefinitions.map(([id,label,Icon,route]) => <button key={id} className={activeTab===id?'active':''} aria-pressed={activeTab===id}
        onClick={() => navigate(id,route)}><Icon size={15}/><span>{label}</span></button>)}
    </nav>
    <QXDataEvidence source="QX system status APIs" dataAsOf={overview.generatedAt} freshness="CURRENT_REQUEST" label="Operational field evidence"/>

    {overviewState.error && <Notice tone="error">{overviewState.error}. Previously loaded operational data, if any, is unchanged.</Notice>}
    {overviewState.loading && !overviewState.data && <p role="status">Loading measured system status...</p>}
    {activeTab === 'overview' && <OverviewPanel overview={overview} loading={overviewState.loading} onRefresh={loadOverview}/>}
    {activeTab === 'providers' && <ProviderPanel/>}
    {activeTab === 'data' && <DataPanel cache={overview.cache} loading={overviewState.loading} onRefresh={loadOverview}/>}
    {activeTab === 'jobs' && <JobsPanel state={jobState} onRefresh={loadJobs}/>}
    {activeTab === 'runs' && <RunsPanel status={overview.runHistoryStatus} runs={overview.runs} loading={overviewState.loading} onRefresh={loadOverview}/>}
    {activeTab === 'rules' && <RulesPanel overview={overview}/>}
  </article>;
}

function OverviewPanel({overview,loading,onRefresh}) {
  return <section className="qx-system-stage" aria-label="System overview">
    <PanelHeader title="Operational readiness" detail="Measured local status; no trading or execution controls" loading={loading} onRefresh={onRefresh}/>
    <div className="qx-system-metrics">
      <Metric label="System" value={overview.status}/><Metric label="Pipeline" value={overview.pipelineVersion}/>
      <Metric label="Rules metadata" value={overview.rulesStatus}/><Metric label="Cache inventory" value={overview.cache.status}/>
      <Metric label="Cache freshness" value={overview.cache.freshnessStatus}/><Metric label="Run store" value={overview.runHistoryStatus}/>
    </div>
    <div className="qx-system-list">
      {overview.components.length ? overview.components.map(component => <div key={component.name}><div><strong>{readable(component.name)}</strong><span>{display(component.detail)}</span></div><StatusBadge value={component.status}/></div>)
        : <Notice>Operational components are unavailable.</Notice>}
    </div>
    <p className="qx-system-provenance">Generated {timestamp(overview.generatedAt)}. Cache inventory does not claim market-data freshness.</p>
  </section>;
}

function DataPanel({cache,loading,onRefresh}) {
  return <section className="qx-system-stage" aria-label="Data status">
    <PanelHeader title="Local bar-data inventory" detail="Measured from data/cache/bars; freshness remains separately unverified" loading={loading} onRefresh={onRefresh}/>
    <div className="qx-system-metrics"><Metric label="Availability" value={cache.status}/><Metric label="Freshness" value={cache.freshnessStatus}/>
      <Metric label="Files" value={number(cache.totalFiles)}/><Metric label="Symbols" value={number(cache.totalSymbols)}/>
      <Metric label="Disk MB" value={number(cache.totalSizeMb)}/><Metric label="Latest file update" value={timestamp(cache.latestModifiedAt)}/></div>
    <div className="qx-system-periods"><h3>Observed cache periods</h3>{Object.keys(cache.periods).length
      ? Object.entries(cache.periods).map(([period,count]) => <span key={period}>{period}: {count}</span>)
      : <span>UNAVAILABLE</span>}</div>
    <Notice>Inventory is source-backed local filesystem evidence. It does not establish completed-session freshness, provider health, or strategy sufficiency.</Notice>
  </section>;
}

function JobsPanel({state,onRefresh}) {
  const job = state.data || buildSystemJobStatus(null);
  return <section className="qx-system-stage" aria-label="Jobs status">
    <PanelHeader title="Local scheduler" detail="Read-only Windows task status; no browser-triggered jobs" loading={state.loading} onRefresh={onRefresh}/>
    {state.error && <Notice tone="error">{state.error}</Notice>}
    <div className="qx-system-metrics"><Metric label="Availability" value={job.status}/><Metric label="Configured" value={job.configured?'YES':'NO'}/>
      <Metric label="Scheduler state" value={job.schedulerState}/><Metric label="Last result" value={job.lastResultLabel||job.lastResult}/>
      <Metric label="Last run" value={timestamp(job.lastRunAt)}/><Metric label="Next run" value={timestamp(job.nextRunAt)}/></div>
    <Notice>Task execution and schedule mutation are not exposed in this consolidated read-only workspace.</Notice>
  </section>;
}

function RunsPanel({status,runs,loading,onRefresh}) {
  return <section className="qx-system-stage" aria-label="Run history">
    <PanelHeader title="Persisted run history" detail="Read-only pipeline, workflow, and command-snapshot records" loading={loading} onRefresh={onRefresh}/>
    <StatusBadge value={status}/>
    {runs.length ? <div className="qx-system-table-wrap"><table className="qx-system-table"><thead><tr><th>Type</th><th>ID</th><th>Recorded</th><th>Status</th><th>Summary</th></tr></thead>
      <tbody>{runs.map(run => <tr key={`${run.runType}-${run.runId}`}><td>{run.runType}</td><td>{run.runId}</td><td>{timestamp(run.createdAt)}</td><td><StatusBadge value={run.status}/></td><td>{display(run.summary)}</td></tr>)}</tbody></table></div>
      : <Notice>{status==='EMPTY'?'No persisted operational runs are available yet.':'Run history is unavailable.'}</Notice>}
  </section>;
}

function RulesPanel({overview}) {
  return <section className="qx-system-stage" aria-label="Rules metadata">
    <PanelHeader title="Canonical configuration metadata" detail="Read-only versions only; rule values are not editable here"/>
    <div className="qx-system-metrics"><Metric label="Pipeline version" value={overview.pipelineVersion}/><Metric label="Rules config version" value={overview.rulesConfigVersion}/><Metric label="Metadata status" value={overview.rulesStatus}/></div>
    <Notice>System does not change Phase 3-10 rules, thresholds, weights, or lifecycle semantics.</Notice>
  </section>;
}

function ProviderPanel() {
  const [status,setStatus]=useState(EMPTY_SCHWAB_STATUS);
  const [credentials,setCredentials]=useState({client_id:'',client_secret:'',redirect_uri:'https://127.0.0.1'});
  const [callbackUrl,setCallbackUrl]=useState('');
  const [authorizationUrl,setAuthorizationUrl]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const safeStatus = useMemo(() => status || EMPTY_SCHWAB_STATUS, [status]);
  const load = async () => { try { const next=await getSchwabCredentialStatus();setStatus(next);setCredentials(previous=>({...previous,redirect_uri:next.redirect_uri||'https://127.0.0.1'})); } catch(error){setMessage(error.message);} };
  useEffect(()=>{load();},[]);
  const act=async(action,success)=>{setBusy(true);setMessage('');try{const next=await action();setStatus(next);setMessage(success);return next;}catch(error){setMessage(error.message);return null;}finally{setBusy(false);}};
  const save=async event=>{event.preventDefault();if(await act(()=>saveSchwabCredentials(credentials),'Credentials saved to the approved local store.'))setCredentials(previous=>({...previous,client_secret:''}));};
  const reauthenticate=async()=>{setBusy(true);setMessage('');try{const result=await getSchwabOAuthUrl();setAuthorizationUrl(result.authorization_url);window.open(result.authorization_url,'_blank','noopener,noreferrer');setMessage('Authorization opened. Paste the complete callback URL below after consent.');}catch(error){setMessage(error.message);}finally{setBusy(false);}};
  const exchange=async event=>{event.preventDefault();if(await act(()=>completeSchwabAuthentication(callbackUrl),'Authentication completed and provider health refreshed.')){setCallbackUrl('');setAuthorizationUrl('');}};
  const clear=async()=>{if(await act(clearSchwabCredentials,'Local credentials and token were cleared.')){setCredentials({client_id:'',client_secret:'',redirect_uri:'https://127.0.0.1'});setCallbackUrl('');setAuthorizationUrl('');}};
  return <section className="qx-system-stage" aria-label="Provider credentials and health">
    <PanelHeader title="Schwab provider" detail="Existing local credential, OAuth, token, and health workflow" loading={busy} onRefresh={load}/>
    <div className="qx-system-metrics"><Metric label="Credentials" value={safeStatus.configured?'CONFIGURED':'NOT CONFIGURED'}/><Metric label="OAuth" value={safeStatus.oauth_status}/>
      <Metric label="Refresh token" value={safeStatus.refresh_token_status}/><Metric label="Market API" value={safeStatus.provider_health}/><Metric label="Last verified" value={timestamp(safeStatus.last_verified_at)}/></div>
    <form className="qx-system-form" onSubmit={save}><h3>Local Schwab Credentials</h3>
      <label>Client ID {safeStatus.client_id_last4?`(saved ending ${safeStatus.client_id_last4})`:''}<input aria-label="Client ID" value={credentials.client_id} onChange={event=>setCredentials(previous=>({...previous,client_id:event.target.value}))} required/></label>
      <label>Client Secret<input aria-label="Client Secret" type="password" autoComplete="new-password" value={credentials.client_secret} onChange={event=>setCredentials(previous=>({...previous,client_secret:event.target.value}))} required/></label>
      <label>Redirect URI<input aria-label="Redirect URI" value={credentials.redirect_uri} onChange={event=>setCredentials(previous=>({...previous,redirect_uri:event.target.value}))} required/></label>
      <div className="qx-system-actions"><button type="submit" disabled={busy}>Save Credentials</button><button type="button" onClick={()=>act(testSchwabConnection,'Schwab provider verification completed.')} disabled={busy||!safeStatus.configured}>Test Connection</button><button type="button" className="danger" onClick={clear} disabled={busy}>Clear Credentials</button></div>
    </form>
    <div className="qx-system-form"><h3>Manual Local OAuth</h3><button type="button" onClick={reauthenticate} disabled={busy||!safeStatus.configured}>Re-authenticate Schwab</button>
      {authorizationUrl&&<a href={authorizationUrl} target="_blank" rel="noreferrer">Open Schwab authorization</a>}
      <p>After authorization, the browser may redirect to https://127.0.0.1 and fail to load. Copy the COMPLETE URL from the address bar and paste it below.</p>
      <form onSubmit={exchange}><label>Schwab Callback URL<input aria-label="Schwab Callback URL" type="password" autoComplete="off" value={callbackUrl} onChange={event=>setCallbackUrl(event.target.value)} required/></label><button type="submit" disabled={busy||!callbackUrl}>Complete Authentication</button></form>
      <small>Temporary local-development workflow. Callback URLs, codes, credentials, and tokens are never shown after submission.</small>
    </div>
    {message&&<p role="status" className="qx-system-message">{message}</p>}
  </section>;
}

function PanelHeader({title,detail,loading=false,onRefresh}) { return <header className="qx-system-panel-header"><div><h2>{title}</h2><p>{detail}</p></div>{onRefresh&&<button type="button" onClick={onRefresh} disabled={loading}><RefreshCw size={14} className={loading?'spin':''}/>{loading?'Refreshing...':'Refresh'}</button>}</header>; }
function Metric({label,value}) { return <div><span>{label}</span><strong>{display(value)}</strong></div>; }
function StatusBadge({value}) { const status=display(value);return <span className={`qx-system-status qx-system-status-${status.toLowerCase().replaceAll(/[^a-z0-9]+/g,'-')}`}><ShieldCheck size={11}/>{status}</span>; }
function Notice({children,tone=''}) { return <p className={`qx-system-notice ${tone}`} role={tone==='error'?'alert':'status'}>{children}</p>; }
function display(value) { return value==null||value===''?'UNAVAILABLE':String(value); }
function readable(value) { return display(value).replaceAll('_',' '); }
function number(value) { return Number.isFinite(value)?value.toLocaleString():'UNAVAILABLE'; }
function timestamp(value) { if(!value)return 'UNAVAILABLE';const parsed=new Date(value);return Number.isFinite(parsed.getTime())?parsed.toLocaleString():String(value); }
